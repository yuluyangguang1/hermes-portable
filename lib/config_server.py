#!/usr/bin/env python3
"""
Hermes Portable — Web 配置面板 v3
风格与 Hermes Web UI (port 9119) 一致
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
# When running from lib/, the portable root is one level up.
# When running from root (legacy), SCRIPT_DIR is already the root.
if SCRIPT_DIR.name == "lib":
    PORTABLE_ROOT = SCRIPT_DIR.parent
else:
    PORTABLE_ROOT = SCRIPT_DIR
DATA_DIR = PORTABLE_ROOT / "data"
PORTABLE_REPO = "yuluyangguang1/hermes-portable"

# ─── Live model catalog (Hermes upstream) ───────────────────────────
# Hermes upstream publishes a JSON manifest of curated, tool-call-capable
# models for OpenRouter and Nous Portal. Pulling it lets users see new
# models without us shipping a new release. Network failures fall back
# silently to the bundled PROVIDERS list below.
#
# Schema: https://hermes-agent.nousresearch.com/docs/reference/model-catalog
MODEL_CATALOG_URL = "https://hermes-agent.nousresearch.com/docs/api/model-catalog.json"
MODEL_CATALOG_CACHE_TTL_SEC = 6 * 3600  # 6 hours
MODEL_CATALOG_CACHE_FILE = DATA_DIR / ".model-catalog-cache.json"
_model_catalog_lock = threading.Lock()
_model_catalog_state = {"data": None, "fetched_at": 0.0}


def _load_catalog_from_disk():
    """Load the persisted catalog cache from disk if recent enough.

    Used so the first request after a fresh launch doesn't have to wait
    for the network round-trip. Caller still validates TTL.
    """
    try:
        if not MODEL_CATALOG_CACHE_FILE.exists():
            return None
        raw = MODEL_CATALOG_CACHE_FILE.read_text(encoding="utf-8")
        cached = json.loads(raw)
        if not isinstance(cached, dict):
            return None
        return cached
    except Exception:
        return None


def _save_catalog_to_disk(payload):
    """Persist the latest catalog to disk so subsequent launches start hot."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MODEL_CATALOG_CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        if hasattr(os, "replace"):
            os.replace(str(tmp), str(MODEL_CATALOG_CACHE_FILE))
        else:
            tmp.rename(MODEL_CATALOG_CACHE_FILE)
    except Exception:
        # Cache miss is non-fatal — we just refetch next time.
        pass


def _fetch_catalog_remote(timeout=8):
    """Fetch the upstream catalog JSON. Returns None on any failure.

    Some portable Python builds end up without a usable system trust
    store (Windows servers, locked-down corp images, USB-stick installs
    where the host cert bundle doesn't follow). Try certifi first if it
    is available, then fall through to the system default. We do NOT
    silently disable verification — losing TLS verification would let a
    captive portal inject a malicious model list. Better to fall back
    to the bundled snapshot than to trust an unverified manifest."""
    import ssl
    contexts = []
    try:
        import certifi  # type: ignore
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    contexts.append(None)  # default context
    for ctx in contexts:
        try:
            req = urllib.request.Request(
                MODEL_CATALOG_URL,
                headers={"User-Agent": "HermesPortable/ConfigServer"},
            )
            kwargs = {"timeout": timeout}
            if ctx is not None:
                kwargs["context"] = ctx
            with urllib.request.urlopen(req, **kwargs) as resp:
                if resp.status != 200:
                    continue
                data = json.loads(resp.read(512 * 1024).decode("utf-8"))
                if isinstance(data, dict) and isinstance(data.get("providers"), dict):
                    return data
                continue
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def get_live_catalog(force_refresh=False):
    """Return the latest model catalog, fetching/caching as needed.

    Caches in memory for MODEL_CATALOG_CACHE_TTL_SEC. On expiry tries the
    network; on failure keeps serving the stale cache (also persisted to
    disk so a brand-new launcher starts with last-known-good).
    """
    now = time.time()
    with _model_catalog_lock:
        cached = _model_catalog_state.get("data")
        fetched_at = _model_catalog_state.get("fetched_at", 0.0)
        if not force_refresh and cached and (now - fetched_at) < MODEL_CATALOG_CACHE_TTL_SEC:
            return cached
        # Try disk cache first if we have nothing in memory
        if not cached:
            disk = _load_catalog_from_disk()
            if disk:
                _model_catalog_state["data"] = disk
                _model_catalog_state["fetched_at"] = disk.get("_fetched_at", 0.0)
                cached = disk
                # If the disk copy is fresh enough, use it without hitting net
                if (now - _model_catalog_state["fetched_at"]) < MODEL_CATALOG_CACHE_TTL_SEC:
                    return cached
        # Stale or missing — try the network
        fresh = _fetch_catalog_remote()
        if fresh is not None:
            fresh = dict(fresh)
            fresh["_fetched_at"] = now
            _model_catalog_state["data"] = fresh
            _model_catalog_state["fetched_at"] = now
            _save_catalog_to_disk(fresh)
            return fresh
        # Network failed — keep serving whatever we have (could be None)
        return cached


def _merge_catalog_into_providers(providers, catalog):
    """Return a new providers list with `models` overridden from the live
    catalog for providers it covers (openrouter, nous). Other providers
    pass through unchanged.

    The catalog only carries an `id` per model. We turn each into the
    same dict shape the bundled list uses (just the id string), so the
    downstream HTML/JS doesn't need to special-case the source. Models
    flagged `recommended` or `free` are surfaced via a `__catalog_meta`
    side-channel so the UI can badge them.
    """
    if not catalog or not isinstance(catalog.get("providers"), dict):
        return providers
    cat_providers = catalog["providers"]
    merged = []
    for p in providers:
        pid = p.get("id")
        cat_entry = cat_providers.get(pid)
        if not cat_entry or not isinstance(cat_entry.get("models"), list):
            merged.append(p)
            continue
        live_ids = []
        live_meta = {}
        for m in cat_entry["models"]:
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            if not isinstance(mid, str) or not mid:
                continue
            live_ids.append(mid)
            desc = m.get("description") or ""
            if desc:
                live_meta[mid] = desc
        if not live_ids:
            merged.append(p)
            continue
        # Stable order: catalog order. Drop duplicates while keeping order.
        seen = set()
        deduped = []
        for mid in live_ids:
            if mid in seen:
                continue
            seen.add(mid)
            deduped.append(mid)
        new_p = dict(p)
        new_p["models"] = deduped
        if live_meta:
            new_p["model_meta"] = live_meta
        new_p["catalog_source"] = "live"
        merged.append(new_p)
    return merged


def _detect_venv_dir():
    """Pick the right venv for the current platform.

    Universal zip ships venv-<platform>/; single-platform zip ships venv/.
    We auto-detect so the config panel works in both layouts.
    """
    import platform as _p
    system = _p.system()
    arch = _p.machine().lower()
    if arch in ("x86_64", "amd64"): arch = "x64"
    elif arch in ("aarch64", "arm64"): arch = "arm64"

    if system == "Darwin":
        label = f"macos-{arch}"
    elif system == "Linux":
        label = f"linux-{arch}"
    elif system == "Windows":
        label = f"windows-{arch}"
    else:
        label = f"{system.lower()}-{arch}"

    for candidate in (PORTABLE_ROOT / f"venv-{label}", PORTABLE_ROOT / "venv"):
        py = (candidate / "Scripts" / "python.exe") if system == "Windows" \
            else (candidate / "bin" / "python")
        if py.exists():
            return candidate
    # Fallback: return the single-platform default even if missing,
    # so downstream error messages stay informative.
    return PORTABLE_ROOT / "venv"


VENV_DIR = _detect_venv_dir()
ENV_FILE = DATA_DIR / ".env"
CONFIG_FILE = DATA_DIR / "config.yaml"

PORT = 17520

# ═══════════════════════════════════════════════════════════════
#  DATA DEFINITIONS
# ═══════════════════════════════════════════════════════════════

PROVIDERS = [
    # NOTE: For OpenRouter and Nous Portal the live model list is fetched
    # from the upstream Hermes catalog at runtime (see get_live_catalog).
    # The lists below are last-known-good snapshots used when the network
    # is unavailable. Keep them roughly in sync with the upstream
    # manifest at https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
    {"id": "openrouter",  "name": "OpenRouter",     "env": "OPENROUTER_API_KEY", "models": [
        "anthropic/claude-fable-5","anthropic/claude-opus-4.8","anthropic/claude-opus-4.8-fast","anthropic/claude-sonnet-5","anthropic/claude-haiku-4.5",
        "openai/gpt-5.6-sol","openai/gpt-5.6-sol-pro","openai/gpt-5.6-terra","openai/gpt-5.6-terra-pro","openai/gpt-5.6-luna","openai/gpt-5.6-luna-pro",
        "openai/gpt-5.5","openai/gpt-5.5-pro","openai/gpt-5.4-mini","openai/gpt-5.4-nano","openai/gpt-5.3-codex",
        "google/gemini-3.5-flash","google/gemini-3-pro-preview","google/gemini-3.1-pro-preview","google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview","google/gemini-3-pro-image-preview",
        "x-ai/grok-4.5","x-ai/grok-4.3","x-ai/grok-4.20",
        "qwen/qwen3.7-max","qwen/qwen3.7-plus","qwen/qwen3.6-plus","qwen/qwen3.6-35b-a3b",
        "deepseek/deepseek-v4-pro","deepseek/deepseek-v4-flash",
        "z-ai/glm-5.2","z-ai/glm-5.1",
        "minimax/minimax-m3","minimax/minimax-m2.7",
        "stepfun/step-3.7-flash","stepfun/step-3.5-flash",
        "xiaomi/mimo-v2.5-pro",
        "tencent/hy3","tencent/hy3:free",
        "nvidia/nemotron-3-super-120b-a12b","nvidia/nemotron-3-super-120b-a12b:free","nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/pareto-code","openrouter/elephant-alpha","openrouter/owl-alpha",
        "sakana/fugu-ultra",
        "poolside/laguna-m.1:free",
        "inclusionai/ring-2.6-1t:free",
    ]},
    {"id": "nous",        "name": "Nous Portal",    "env": "NOUS_API_KEY",       "models": [
        "anthropic/claude-fable-5","anthropic/claude-opus-4.8","anthropic/claude-sonnet-5","anthropic/claude-haiku-4.5",
        "openai/gpt-5.6-sol","openai/gpt-5.6-sol-pro","openai/gpt-5.6-terra","openai/gpt-5.6-terra-pro","openai/gpt-5.6-luna","openai/gpt-5.6-luna-pro",
        "openai/gpt-5.5","openai/gpt-5.5-pro","openai/gpt-5.4-mini","openai/gpt-5.4-nano","openai/gpt-5.3-codex",
        "google/gemini-3.5-flash","google/gemini-3-pro-preview","google/gemini-3.1-pro-preview","google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview",
        "x-ai/grok-4.5","x-ai/grok-4.3",
        "qwen/qwen3.7-max","qwen/qwen3.7-plus","qwen/qwen3.6-plus","qwen/qwen3.6-35b-a3b",
        "deepseek/deepseek-v4-pro","deepseek/deepseek-v4-flash",
        "z-ai/glm-5.2","z-ai/glm-5.1",
        "minimax/minimax-m3","minimax/minimax-m2.7",
        "stepfun/step-3.7-flash","stepfun/step-3.5-flash",
        "xiaomi/mimo-v2.5-pro",
        "tencent/hy3",
        "nvidia/nemotron-3-super-120b-a12b",
        "sakana/fugu-ultra",
        "nousresearch/hermes-4-405b","nousresearch/hermes-4-70b",
        "nousresearch/deephermes-3-mistral-24b",
    ]},
    {"id": "anthropic",   "name": "Anthropic",      "env": "ANTHROPIC_API_KEY",  "models": [
        "claude-fable-5","claude-opus-4.8","claude-opus-4.8-fast","claude-sonnet-5","claude-opus-4-7","claude-opus-4-6","claude-sonnet-4-6","claude-haiku-4-5",
        "claude-haiku-4-5-20251001","claude-sonnet-4-20250514","claude-opus-4-20250514",
        "claude-3-7-sonnet-latest","claude-3-5-haiku-latest",
    ]},
    {"id": "openai",      "name": "OpenAI",         "env": "OPENAI_API_KEY",     "models": [
        "gpt-5.6-sol","gpt-5.6-sol-pro","gpt-5.6-terra","gpt-5.6-terra-pro","gpt-5.6-luna","gpt-5.6-luna-pro","gpt-5.5","gpt-5.5-pro","gpt-5.5-mini",
        "gpt-5.4","gpt-5.4-mini","gpt-5.4-nano",
        "gpt-5.3-codex","gpt-5.2","gpt-5","gpt-5-mini","gpt-5-nano",
        "o3","o3-mini","o4-mini","gpt-4.1","gpt-4.1-mini",
    ]},
    {"id": "deepseek",    "name": "DeepSeek",       "env": "DEEPSEEK_API_KEY",   "models": [
        "deepseek-v4-pro","deepseek-v4-flash","deepseek-v3.2-speciale","deepseek-v3.2",
        "deepseek-chat","deepseek-reasoner",
    ]},
    {"id": "google",      "name": "Google Gemini",  "env": "GOOGLE_API_KEY",     "models": [
        "gemini-3.5-flash","gemini-3-pro-preview","gemini-3.1-pro-preview","gemini-3.1-flash-lite-preview",
        "gemini-3-pro-preview","gemini-3-flash-preview","gemini-3-pro-image-preview",
        "gemini-2.5-pro","gemini-2.5-flash","gemini-2.5-flash-lite","gemini-2.5-flash-image-preview",
    ]},
    # ⚠ xAI 已于 2026-05-15 退役 grok-4 / grok-4-fast / grok-4-1-fast / grok-code-fast-1 / grok-3
    # 5月新发布 grok-4.20 (catalog confirms)
    {"id": "xai",         "name": "xAI Grok",       "env": "XAI_API_KEY",        "models": [
        "grok-4.5","grok-4.3","grok-4.20",
    ]},
    {"id": "mistral",     "name": "Mistral AI",     "env": "MISTRAL_API_KEY",    "models": [
        "mistral-large-3","mistral-large-2411","mistral-medium-latest","mistral-small-latest",
        "ministral-3b-latest","ministral-8b-latest","codestral-latest","pixtral-large-latest",
    ]},
    {"id": "zhipu",       "name": "Zhipu GLM",      "env": "ZHIPU_API_KEY",      "models": [
        "glm-5.2","glm-5.1","glm-5","glm-5-turbo","glm-4.7","glm-4.6","glm-4.5-air","glm-4.5-flash",
    ]},
    {"id": "dashscope",   "name": "Alibaba DashScope","env": "DASHSCOPE_API_KEY","models": [
        "qwen3.7-max","qwen3.7-plus","qwen3.6-max","qwen3.6-plus","qwen3.6-35b-a3b",
        "qwen3-max","qwen3-max-2026-01-23","qwen3-max-preview","qwen3-coder-plus","qwen3-coder-next",
        "qwen3-vl-plus","qwen3-omni-flash",
        "qwen-max-latest","qwen-plus-latest","qwen-turbo-latest","qwen-long",
    ]},
    {"id": "kimi",        "name": "Kimi / Moonshot","env": "KIMI_API_KEY",       "models": [
        "kimi-k2.7-code","kimi-k2.6","kimi-k2.5","kimi-k2-thinking-turbo","kimi-k2-thinking",
        "moonshot-v1-128k","moonshot-v1-32k",
    ]},
    {"id": "minimax",     "name": "MiniMax",        "env": "MINIMAX_API_KEY",    "models": [
        "MiniMax-M3","MiniMax-M2.7","MiniMax-M2.7-highspeed","MiniMax-M2.5","MiniMax-M2.5-highspeed","MiniMax-M2",
    ]},
    {"id": "xiaomi",      "name": "Xiaomi MiMo",    "env": "XIAOMI_API_KEY",     "models": [
        "xiaomi/mimo-v2.5-pro","xiaomi/mimo-v2-pro","xiaomi/mimo-v2-flash",
    ]},
    {"id": "doubao",      "name": "豆包 / 火山引擎", "env": "DOUBAO_API_KEY",     "models": [
        "doubao-seed-1.6","doubao-seed-1.6-thinking","doubao-1.5-pro-256k","doubao-1.5-pro-32k","doubao-1.5-lite-32k",
    ]},
    {"id": "groq",        "name": "Groq",           "env": "GROQ_API_KEY",       "models": [
        "llama-3.3-70b-versatile","llama-3.1-8b-instant",
        "meta-llama/llama-4-scout-17b-16e-instruct","meta-llama/llama-4-maverick-17b-128e-instruct",
        "qwen/qwen3-32b","deepseek-r1-distill-llama-70b","moonshotai/kimi-k2-instruct","groq/compound",
    ]},
    {"id": "cerebras",    "name": "Cerebras",       "env": "CEREBRAS_API_KEY",   "models": [
        "llama-4-scout-17b-16e-instruct","llama-4-maverick-17b-128e-instruct",
        "llama3.3-70b","qwen-3-coder-480b","qwen-3-32b",
    ]},
    {"id": "perplexity",  "name": "Perplexity",     "env": "PERPLEXITY_API_KEY", "models": [
        "sonar","sonar-pro","sonar-reasoning","sonar-reasoning-pro","sonar-deep-research",
    ]},
    {"id": "huggingface", "name": "HuggingFace",    "env": "HF_TOKEN",           "models": [
        "Qwen/Qwen3.5-72B-Instruct","deepseek-ai/DeepSeek-V3.2",
        "meta-llama/Llama-4-Scout-17B-16E-Instruct","mistralai/Mistral-Small-3.2-24B-Instruct",
    ]},
    {"id": "nvidia",      "name": "NVIDIA NIM",     "env": "NVIDIA_API_KEY",     "models": [
        "nvidia/llama-3.3-nemotron-super-49b-v1","nvidia/llama-3.1-nemotron-ultra-253b-v1",
        "meta/llama-4-maverick-17b-128e-instruct","deepseek-ai/deepseek-r1",
    ]},
    {"id": "stepfun",     "name": "StepFun 阶跃",   "env": "STEPFUN_API_KEY",    "models": [
        "step-3.7-flash","step-3.5-flash","step-3.5","step-2-16k","step-1v-8k",
    ]},
    {"id": "novita",      "name": "NovitaAI",       "env": "NOVITA_API_KEY",     "models": [
        "deepseek/deepseek-v4-pro","meta/llama-4-maverick-17b-128e-instruct",
        "qwen/qwen3-32b","mistralai/mistral-small-3.2-24b-instruct",
    ]},
    {"id": "ollama",      "name": "Ollama Cloud",   "env": "OLLAMA_API_KEY",     "models": [
        "llama3.3","qwen3","deepseek-v4","mistral-small",
    ]},
    {"id": "copilot",     "name": "GitHub Copilot",  "env": "GITHUB_TOKEN",       "models": [
        "gpt-4o","gpt-4o-mini","claude-sonnet-4","o3-mini",
    ]},
    {"id": "together",    "name": "Together AI",      "env": "TOGETHER_API_KEY",      "models": [
        "meta-llama/Llama-4-Scout-17B-16E-Instruct","meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "deepseek-ai/DeepSeek-V3.2","Qwen/Qwen3-235B-A22B","mistralai/Mistral-Small-3.2-24B-Instruct",
    ]},
    {"id": "fireworks",   "name": "Fireworks AI",    "env": "FIREWORKS_API_KEY",     "models": [
        "accounts/fireworks/models/llama4-scout-instruct-basic","accounts/fireworks/models/deepseek-v4-pro",
        "accounts/fireworks/models/qwen3-235b-a22b","accounts/fireworks/models/mixtral-8x22b-instruct",
    ]},
    {"id": "cohere",      "name": "Cohere",          "env": "COHERE_API_KEY",        "models": [
        "command-a","command-r-plus","command-r","command-light",
    ]},
    {"id": "replicate",   "name": "Replicate",       "env": "REPLICATE_API_TOKEN",   "models": [
        "meta/llama-4-scout-17b-16e-instruct","deepseek-ai/deepseek-v4-pro",
        "mistralai/mistral-small-3.2-24b-instruct",
    ]},
    {"id": "baidu",       "name": "百度文心",         "env": "BAIDU_API_KEY",          "models": [
        "ernie-4.5-turbo-128k","ernie-x1-turbo","ernie-4.5-8k","ernie-4.0-8k","ernie-3.5-8k","ernie-speed-128k",
    ]},
    {"id": "baichuan",    "name": "百川智能",         "env": "BAICHUAN_API_KEY",       "models": [
        "Baichuan4","Baichuan3-Turbo","Baichuan2-Turbo",
    ]},
    {"id": "yi",          "name": "零一万物",         "env": "YI_API_KEY",             "models": [
        "yi-large","yi-medium","yi-spark","yi-lightning",
    ]},
    {"id": "sambanova",   "name": "SambaNova",       "env": "SAMBANOVA_API_KEY",      "models": [
        "Meta-Llama-3.3-70B-Instruct","DeepSeek-V3-0324","Qwen3-32B",
    ]},
    {"id": "cloudflare",  "name": "Cloudflare AI",   "env": "CLOUDFLARE_API_TOKEN",   "models": [
        "@cf/meta/llama-3.3-70b-instruct-fp8","@cf/deepseek-ai/deepseek-v3","@cf/qwen/qwen3-32b",
    ]},
        {"id": "tencent",     "name": "腾讯混元",       "env": "TENCENT_API_KEY",     "models": [
        "hunyuan-turbo","hunyuan-large","hunyuan-pro","hunyuan-standard",
    ],
     "key_hint": "粘贴腾讯 API Key", "note": "腾讯混元，Turbo 最新",
     "tags": ["cn"]},
        {"id": "iflytek",     "name": "讯飞星火",       "env": "IFLYTEK_API_KEY",     "models": [
        "spark-max","spark-pro","spark-lite",
    ],
     "key_hint": "粘贴讯飞 API Key", "note": "讯飞星火，Max 最新",
     "tags": ["cn"]},
    {"id": "siliconflow", "name": "硅基流动",         "env": "SILICONFLOW_API_KEY",    "models": [
        "deepseek-ai/DeepSeek-V4-Pro","Qwen/Qwen3-235B-A22B",
        "meta-llama/Llama-4-Scout-17B-Instruct","Pro/deepseek-ai/DeepSeek-R1",
    ]},
    {"id": "coze",       "name": "Coze / 扣子",    "env": "COZE_API_KEY",       "models": [
        "coze-gpt-4o","coze-claude-3.5-sonnet","coze-gemini-1.5-pro",
    ],
     "key_hint": "粘扣子 API Key", "note": "字节跳动扣子平台，多模型",
     "tags": ["cn"]},
    {"id": "volcengine",  "name": "火山引擎",       "env": "VOLCENGINE_API_KEY",  "models": [
        "doubao-seed-1.6","doubao-seed-1.6-thinking","doubao-1.5-pro-256k",
    ],
     "key_hint": "粘火山引擎 API Key", "note": "字节跳动火山引擎，豆包直连",
     "tags": ["cn"]},
    {"id": "alibaba",    "name": "阿里云",         "env": "ALIBABA_API_KEY",     "models": [
        "qwen3.7-max","qwen3.7-plus","qwen3.6-max","qwen3.6-plus",
    ],
     "key_hint": "粘阿里云 API Key", "note": "阿里云，通义千问直连",
     "tags": ["cn"]},
    {"id": "amazon",     "name": "Amazon Bedrock", "env": "AMAZON_API_KEY",     "models": [
        "nova-premier-v1","nova-pro-v1","nova-lite-v1","nova-micro-v1",
    ],
     "key_hint": "粘贴 AWS Bedrock API Key", "note": "Amazon Nova 系列，AWS 原生",
     "tags": []},
    {"id": "deepinfra",  "name": "DeepInfra",      "env": "DEEPINFRA_API_KEY",  "models": [
        "deepseek-ai/DeepSeek-V4-Pro","meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct","zai-org/GLM-5.1",
    ],
     "key_hint": "粘贴 DeepInfra API Key", "note": "极低价格开源模型",
     "tags": ["cheap"]},
    {"id": "lmstudio",    "name": "LM Studio",      "env": "LMSTUDIO_API_KEY",   "models": [],
     "key_hint": "本地 LM Studio", "note": "本地模型，无需 API Key",
     "tags": []},
    {"id": "gmi",         "name": "GMI Cloud",      "env": "GMI_API_KEY",        "models": [
        "deepseek-ai/DeepSeek-V4-Pro","meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    ],
     "key_hint": "粘贴 GMI API Key", "note": "GMI 云推理",
     "tags": []},
    {"id": "kilocode",    "name": "Kilo Code",      "env": "KILOCODE_API_KEY",   "models": [
        "gpt-5.5","claude-opus-4-7","gemini-3-pro-preview",
    ],
     "key_hint": "粘贴 Kilo Code API Key", "note": "代码助手",
     "tags": []},
    {"id": "ai-gateway",  "name": "Vercel AI Gateway","env": "VERCEL_API_KEY",    "models": [
        "gpt-5.5","claude-opus-4-7","gemini-3-pro-preview",
    ],
     "key_hint": "粘贴 Vercel API Key", "note": "Vercel AI 网关",
     "tags": []},
    {"id": "longcat",     "name": "LongCat",        "env": "LONGCAT_API_KEY",    "models": [
        "LongCat-Flash-Lite","LongCat-2.0-Preview",
    ],
     "key_hint": "粘贴 LongCat API Key", "note": "长猫模型",
     "tags": []},
    {"id": "arcee",       "name": "Arcee AI",       "env": "ARCEE_API_KEY",      "models": [
        "arcee-large","arcee-small",
    ],
     "key_hint": "粘贴 Arcee API Key", "note": "Arcee 模型",
     "tags": []},
    {"id": "zai",         "name": "Z.AI / 智谱",    "env": "ZAI_API_KEY",        "models": [
        "glm-5.2","glm-5.1","glm-5","glm-5v-turbo","glm-5-turbo","glm-4.7","glm-4.5","glm-4.5-flash",
    ],
     "key_hint": "粘贴 Z.AI API Key", "note": "智谱直连",
     "tags": ["cn"]},
    {"id": "glm",         "name": "GLM 代码计划",    "env": "GLM_API_KEY",        "models": [
        "glm-5.2","glm-5.1","glm-5v-turbo","glm-4.7",
    ],
     "key_hint": "粘贴 GLM API Key", "note": "智谱代码计划",
     "tags": ["cn"]},
    {"id": "kimi-coding", "name": "Kimi 代码版",    "env": "KIMI_CODING_API_KEY","models": [
        "kimi-k2.7-code","kimi-k2.6","kimi-k2.5","kimi-for-coding","kimi-k2-thinking","kimi-k2-thinking-turbo",
    ],
     "key_hint": "粘贴 Kimi API Key", "note": "Kimi 代码版",
     "tags": ["cn"]},
    {"id": "kimi-coding-cn","name": "Kimi 中国代码版","env": "KIMI_CODING_CN_API_KEY","models": [
        "kimi-k2.6","kimi-k2.5","kimi-k2-thinking","kimi-k2-turbo-preview",
    ],
     "key_hint": "粘贴 Kimi API Key", "note": "Kimi 中国代码版",
     "tags": ["cn"]},
    {"id": "minimax-cn",  "name": "MiniMax 中国版", "env": "MINIMAX_CN_API_KEY",  "models": [
        "MiniMax-M3","MiniMax-M2.7","MiniMax-M2.7-highspeed","MiniMax-M2.5","MiniMax-M2.5-highspeed",
    ],
     "key_hint": "粘贴 MiniMax API Key", "note": "MiniMax 中国版",
     "tags": ["cn"]},
    {"id": "alibaba-coding-plan","name": "阿里云代码计划","env": "ALIBABA_CODING_API_KEY","models": [
        "qwen3.7-max","qwen3.7-plus","qwen3.6-max","qwen3.6-plus",
    ],
     "key_hint": "粘贴阿里云 API Key", "note": "阿里云代码计划",
     "tags": ["cn"]},
    {"id": "xiaomi-token-plan","name": "小米 Token 计划","env": "XIAOMI_TOKEN_API_KEY","models": [
        "xiaomi/mimo-v2.5-pro","xiaomi/mimo-v2-pro","xiaomi/mimo-v2-flash",
    ],
     "key_hint": "粘贴小米 API Key", "note": "小米 Token 计划",
     "tags": ["cn"]},
    {"id": "tencent-tokenhub","name": "腾讯 TokenHub","env": "TENCENT_TOKENHUB_API_KEY","models": [
        "hy3-preview",
    ],
     "key_hint": "粘贴腾讯 API Key", "note": "腾讯 TokenHub",
     "tags": ["cn"]},
    {"id": "fun-codex",   "name": "Codex-apikey.fun","env": "FUN_CODEX_API_KEY",  "models": [
        "gpt-5.5","gpt-5.4","gpt-5.4-mini","gpt-5.3-codex","gpt-5.3-codex-spark",
    ],
     "key_hint": "粘贴 apikey.fun Key", "note": "Codex 中转站",
     "tags": []},
    {"id": "fun-claude",  "name": "Claude-apikey.fun","env": "FUN_CLAUDE_API_KEY", "models": [
        "claude-opus-4-8","claude-opus-4-7","claude-opus-4-6","claude-sonnet-4-6","claude-haiku-4-5",
    ],
     "key_hint": "粘贴 apikey.fun Key", "note": "Claude 中转站",
     "tags": []},
    {"id": "cliproxyapi", "name": "CLIProxyAPI",    "env": "CLIPROXYAPI_API_KEY", "models": [
        "gpt-5.5","claude-opus-4-7","gemini-3-pro-preview",
    ],
     "key_hint": "粘贴 CLIProxy Key", "note": "CLI 代理 API",
     "tags": []},
    {"id": "opencode-zen","name": "OpenCode Zen",   "env": "OPENCODE_ZEN_API_KEY","models": [
        "gpt-5.5","claude-opus-4-7","gemini-3-pro-preview",
    ],
     "key_hint": "粘贴 OpenCode Key", "note": "OpenCode Zen",
     "tags": []},
    {"id": "opencode-go", "name": "OpenCode Go",    "env": "OPENCODE_GO_API_KEY", "models": [
        "gpt-5.5","claude-opus-4-7","gemini-3-pro-preview",
    ],
     "key_hint": "粘贴 OpenCode Key", "note": "OpenCode Go",
     "tags": []},
    {"id": "claude-oauth","name": "Claude OAuth",   "env": "CLAUDE_OAUTH_TOKEN",  "models": [
        "claude-fable-5","claude-opus-4-8","claude-opus-4-7","claude-opus-4-6","claude-sonnet-4-6","claude-haiku-4-5",
    ],
     "key_hint": "OAuth 认证", "note": "Claude OAuth 认证",
     "tags": []},
    {"id": "google-gemini-cli","name": "Google Gemini OAuth","env": "GOOGLE_GEMINI_CLI_TOKEN","models": [
        "gemini-3.1-pro-preview","gemini-3-pro-preview","gemini-3-flash-preview",
    ],
     "key_hint": "OAuth 认证", "note": "Google Gemini OAuth",
     "tags": []},
    {"id": "xai-oauth",  "name": "xAI Grok OAuth", "env": "XAI_OAUTH_TOKEN",     "models": [
        "grok-4.5","grok-4.3","grok-4.20-0309-reasoning","grok-4.20-0309-non-reasoning",
    ],
     "key_hint": "OAuth 认证", "note": "xAI Grok OAuth",
     "tags": []},
    {"id": "openai-codex","name": "OpenAI Codex",   "env": "OPENAI_CODEX_API_KEY","models": [
        "gpt-5.5","gpt-5.4","gpt-5.3-codex",
    ],
     "key_hint": "粘贴 OpenAI Key", "note": "OpenAI Codex 直连",
     "tags": []},
    {"id": "custom",      "name": "自定义 / 中转站", "env": "CUSTOM_API_KEY",
     "base_url_env": "CUSTOM_BASE_URL",
     "custom_model": True,
     "models": ["gpt-5.5","gpt-5.5-pro","claude-opus-4-7","claude-sonnet-4-6","gemini-3.1-pro-preview","deepseek-v4-pro","grok-4.3","kimi-k2.6"]},
]

CHANNELS = [
    {
        "id": "telegram", "name": "Telegram", "icon": "✈",
        "desc": "Telegram Bot 消息",
        "fields": [
            {"key": "TELEGRAM_BOT_TOKEN", "label": "Bot Token", "placeholder": "123456:ABC-DEF...", "type": "password"},
            {"key": "TELEGRAM_CHAT_ID",   "label": "Chat ID (可选)", "placeholder": "Chat ID for messages", "type": "text"},
        ],
    },
    {
        "id": "discord", "name": "Discord", "icon": "◆",
        "desc": "Discord Bot 消息",
        "fields": [
            {"key": "DISCORD_BOT_TOKEN", "label": "Bot Token", "placeholder": "MTIz...", "type": "password"},
        ],
    },
    {
        "id": "slack", "name": "Slack", "icon": "◈",
        "desc": "Slack Bot 消息",
        "fields": [
            {"key": "SLACK_BOT_TOKEN",   "label": "Bot Token (xoxb-...)", "placeholder": "xoxb-...", "type": "password"},
            {"key": "SLACK_SIGNING_SECRET", "label": "签名密钥", "placeholder": "abc123...", "type": "password"},
        ],
    },
    {
        "id": "whatsapp", "name": "WhatsApp", "icon": "▣",
        "desc": "WhatsApp 消息 (via Baileys)",
        "fields": [
            {"key": "WHATSAPP_ENABLED", "label": "启用", "placeholder": "true", "type": "text"},
        ],
    },
    {
        "id": "weixin", "name": "WeChat", "icon": "▣",
        "desc": "微信 ilink 平台",
        "fields": [
            {"key": "WEIXIN_TOKEN",      "label": "Bot Token",    "placeholder": "ilink Bot Token", "type": "password"},
            {"key": "WEIXIN_ACCOUNT_ID", "label": "Account ID",   "placeholder": "WeChat Account ID", "type": "text"},
        ],
    },
    {
        "id": "email", "name": "Email", "icon": "✉",
        "desc": "邮件收发 (IMAP/SMTP)",
        "fields": [
            {"key": "EMAIL_IMAP_HOST", "label": "IMAP 服务器", "placeholder": "imap.gmail.com", "type": "text"},
            {"key": "EMAIL_IMAP_PORT", "label": "IMAP 端口", "placeholder": "993", "type": "text"},
            {"key": "EMAIL_SMTP_HOST", "label": "SMTP 服务器", "placeholder": "smtp.gmail.com", "type": "text"},
            {"key": "EMAIL_SMTP_PORT", "label": "SMTP 端口", "placeholder": "587", "type": "text"},
            {"key": "EMAIL_ADDRESS",   "label": "邮箱地址", "placeholder": "you@gmail.com", "type": "text"},
            {"key": "EMAIL_PASSWORD",  "label": "密码 / App 密码", "placeholder": "xxxx xxxx xxxx", "type": "password"},
        ],
    },
    {
        "id": "signal", "name": "Signal", "icon": "◆",
        "desc": "Signal 消息 (需要 signal-cli)",
        "fields": [
            {"key": "SIGNAL_PHONE_NUMBER", "label": "手机号",  "placeholder": "+86...", "type": "text"},
            {"key": "SIGNAL_CLI_PATH",     "label": "signal-cli 路径", "placeholder": "/usr/local/bin/signal-cli", "type": "text"},
        ],
    },
    {
        "id": "matrix", "name": "Matrix", "icon": "◈",
        "desc": "Matrix 协议消息",
        "fields": [
            {"key": "MATRIX_HOMESERVER", "label": "Homeserver 地址", "placeholder": "https://matrix.org", "type": "text"},
            {"key": "MATRIX_USER",       "label": "用户名",  "placeholder": "@user:matrix.org", "type": "text"},
            {"key": "MATRIX_TOKEN",      "label": "访问令牌", "placeholder": "syt_...", "type": "password"},
        ],
    },
]

# ═══════════════════════════════════════════════════════════════
#  CONFIG READ/WRITE @@
# ═══════════════════════════════════════════════════════════════
#  HERMES WEB UI INTEGRATION
# ═══════════════════════════════════════════════════════════════

WEB_UI_PORT = 8648

def webui_status():
    """Check if hermes-web-ui is running."""
    import subprocess
    try:
        result = subprocess.run(
            ['hermes-web-ui', 'status'],
            capture_output=True, text=True, timeout=5
        )
        return 'running' in result.stdout.lower()
    except Exception:
        return False

def webui_start():
    """Start hermes-web-ui."""
    import subprocess
    try:
        subprocess.Popen(
            ['hermes-web-ui', 'start', str(WEB_UI_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False

def webui_stop():
    """Stop hermes-web-ui."""
    import subprocess
    try:
        subprocess.run(['hermes-web-ui', 'stop'], capture_output=True, timeout=5)
        return True
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════

def parse_env():
    keys = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                # Strip matching surrounding quotes: KEY="value" → value
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                keys[k.strip()] = v
    return keys

def parse_yaml_safe(path):
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def read_config():
    env = parse_env()
    cfg = parse_yaml_safe(CONFIG_FILE)
    # Try to merge the upstream catalog over the bundled provider list.
    # Network failure → silently falls through to bundled list, so the
    # UI never breaks regardless of connectivity.
    catalog = get_live_catalog()
    providers = _merge_catalog_into_providers(PROVIDERS, catalog) if catalog else PROVIDERS
    active_provider = "openrouter"
    for p in providers:
        if env.get(p["env"]):
            active_provider = p["id"]
            break
    return {
        "env": env,
        "config": cfg,
        "providers": providers,
        "channels": CHANNELS,
        "active_provider": active_provider,
        "catalog_updated_at": (catalog or {}).get("updated_at") if catalog else None,
    }

def _yaml_dump_simple(d, indent=0):
    """Minimal YAML writer — no PyYAML dependency."""
    lines = []
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.extend(_yaml_dump_simple(v, indent + 1))
        elif isinstance(v, bool):
            lines.append(f"{prefix}{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{prefix}{k}: {v}")
        elif v is None:
            lines.append(f"{prefix}{k}:")
        else:
            # YAML double-quoted string: escape backslashes and quotes, and
            # flatten newlines. Keeps the output parseable by any YAML reader.
            s = str(v)
            s = s.replace("\\", "\\\\").replace('"', '\\"')
            s = s.replace("\n", "\\n").replace("\r", "\\r")
            lines.append(f'{prefix}{k}: "{s}"')
    return lines



def _atomic_write_text(path, content, encoding="utf-8"):
    """原子写文件：先写 tmp，再 rename。防止半写状态损坏文件。"""
    import os as _os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    try:
        if hasattr(_os, "replace"):
            _os.replace(str(tmp), str(path))  # 跨平台原子替换
        else:
            tmp.rename(path)
    except Exception:
        try: tmp.unlink()
        except Exception: pass
        raise



def _sanitize_env_value(v):
    """清理环境变量值：去除换行符防止破坏 .env 格式。"""
    if v is None:
        return ""
    s = str(v)
    # 拒绝包含换行的值
    if "\n" in s or "\r" in s:
        s = s.replace("\n", "").replace("\r", "")
    return s

_save_config_lock = threading.Lock()


def _known_env_keys():
    """Every env key our UI knows about (providers + channels).

    Used by save_config() to detect "extras" — keys that exist in
    data/.env but aren't in the schema (e.g. WEIXIN_BASE_URL, which
    wechat_check_status() persists after a successful QR login). Without
    this carry-forward, every UI save would clobber those keys silently
    and the WeChat login would have to be redone on next launch.
    """
    keys = set()
    for p in PROVIDERS:
        keys.add(p["env"])
        if p.get("base_url_env"):
            keys.add(p["base_url_env"])
    for ch in CHANNELS:
        for field in ch.get("fields", []):
            keys.add(field["key"])
    return keys


def save_config(data):
    # Serialize concurrent saves: ThreadingHTTPServer can dispatch two
    # POST /api/save requests in parallel, and without this lock both
    # would race on parse_env() → write tmp → os.replace. The atomic
    # rename gives per-write atomicity but not "two concurrent saves
    # both land": the second write blindly overwrites the first.
    # _save_config_lock was defined but never acquired pre-fix.
    with _save_config_lock:
        return _save_config_locked(data)


def _save_config_locked(data):
    lines = []
    lines.append("# ═══════════════════════════════════════════")
    lines.append("#  Hermes Portable — Environment Variables")
    lines.append("# ═══════════════════════════════════════════")
    lines.append("")
    lines.append("# ── LLM Provider API Keys ──")
    for p in PROVIDERS:
        val = data.get("env", {}).get(p["env"], "")
        if val:
            val = _sanitize_env_value(val)
            lines.append(f"{p['env']}={val}")
        else:
            lines.append(f"# {p['env']}=")
    lines.append("")
    lines.append("# ── Messaging Channel Tokens ──")
    for ch in CHANNELS:
        for field in ch["fields"]:
            val = data.get("env", {}).get(field["key"], "")
            if val:
                val = _sanitize_env_value(val)
                lines.append(f"{field['key']}={val}")
            else:
                lines.append(f"# {field['key']}=")

    # ── Preserve out-of-schema keys ──
    # Some keys are written to .env by code paths that don't go through
    # the form (e.g. WEIXIN_BASE_URL set by the WeChat QR-login flow).
    # Read the on-disk .env, find anything we don't know about, and
    # carry it forward. Without this, every save click silently nuked
    # those keys and broke the feature on the next launch.
    known = _known_env_keys()
    submitted_env = data.get("env") or {}
    extras = {}
    # Source 1: keys the frontend included in its POST body. We accept
    # them only if they're not in `known` (so frontend can't bypass the
    # schema validation we'd add later) AND look like reasonable env
    # keys (uppercase + digits + underscores, can't shadow a comment).
    for k, v in submitted_env.items():
        if k in known or not v:
            continue
        if not k or not all(c.isalnum() or c == "_" for c in k) or not k[0].isalpha():
            continue
        extras[k] = v
    # Source 2: keys already on disk that the frontend didn't echo back
    # (true unknowns from out-of-band writers). On-disk wins ties with
    # the submitted set if we've already seen the key.
    try:
        on_disk = parse_env()
    except Exception:
        on_disk = {}
    for k, v in on_disk.items():
        if k in known or not v or k in extras:
            continue
        if not k or not all(c.isalnum() or c == "_" for c in k) or not k[0].isalpha():
            continue
        extras[k] = v
    if extras:
        lines.append("")
        lines.append("# ── Other (preserved across saves) ──")
        for k in sorted(extras):
            lines.append(f"{k}={_sanitize_env_value(extras[k])}")

    lines.append("")
    _atomic_write_text(ENV_FILE, "\n".join(lines), encoding="utf-8")

    model_name = data.get("model_name", "")
    provider = data.get("model_provider", "openrouter")
    cfg = {
        "model": {
            "default": model_name if "/" in model_name else f"{provider}/{model_name}",
            "provider": provider,
        },
        "agent": {
            "max_turns": int(data.get("max_turns", 90)),
        },
        "terminal": {
            "backend": "local",
            "timeout": int(data.get("timeout", 180)),
        },
        "compression": {
            "enabled": data.get("compression", True),
            "threshold": float(data.get("compression_threshold", 0.50)),
            "target_ratio": 0.20,
        },
        "display": {
            "skin": data.get("skin", "default"),
            "tool_progress": data.get("show_tool_progress", True),
            "show_cost": data.get("show_cost", True),
        },
        "memory": {
            "memory_enabled": data.get("memory_enabled", True),
            "user_profile_enabled": True,
        },
    }
    enabled_channels = data.get("enabled_channels", [])
    if enabled_channels:
        cfg["gateway"] = {"enabled": True, "platforms": {}}
        for ch_id in enabled_channels:
            ch = next((c for c in CHANNELS if c["id"] == ch_id), None)
            if ch:
                cfg["gateway"]["platforms"][ch_id] = {"enabled": True}

    _atomic_write_text(CONFIG_FILE, "\n".join(_yaml_dump_simple(cfg)) + "\n", encoding="utf-8")
    return True


# ═══════════════════════════════════════════════════════════════
#  WeChat (iLink) QR-login flow
# ═══════════════════════════════════════════════════════════════
#
# Hermes upstream supports WeChat via the iLink Bot API. Users normally
# complete login via `hermes gateway setup`, which prints a terminal-
# rendered QR code. We replicate that flow here so users can scan from
# the config panel without dropping to the CLI. Same iLink surface
# OpenClaw uses.
#
# On confirm we save WEIXIN_TOKEN, WEIXIN_ACCOUNT_ID, and WEIXIN_BASE_URL
# to data/.env where hermes' Weixin adapter reads them at startup. Spec:
#   https://hermes-agent.nousresearch.com/docs/user-guide/messaging/weixin

ILINK_DEFAULT_BASE = "https://ilinkai.weixin.qq.com"
ILINK_BOT_TYPE = "3"
ILINK_QR_POLL_TIMEOUT_SEC = 35
ILINK_LOGIN_TTL_SEC = 5 * 60
ILINK_MAX_QR_REFRESH = 3
# Cap on concurrent in-flight QR sessions. Anything from localhost can
# POST /api/wechat/start (no auth — by design, this is a localhost-only
# panel), so without a cap, a buggy or hostile localhost process could
# fill _wechat_logins. The TTL cleanup runs on every start/check call,
# so the live count is roughly proportional to legitimate concurrent
# users. A handful of slots is plenty for a single-user portable
# install. Hitting the cap returns a clear error so the UI can show it.
ILINK_MAX_ACTIVE_LOGINS = 16

_wechat_logins = {}
_wechat_lock = threading.Lock()


def _wechat_cleanup_expired_locked():
    """Drop login sessions older than the TTL. Caller holds _wechat_lock."""
    now = time.time()
    stale = [k for k, v in _wechat_logins.items()
             if now - v.get("started_at", 0) > ILINK_LOGIN_TTL_SEC]
    for k in stale:
        _wechat_logins.pop(k, None)


def _ilink_request(path, base_url=None, method="GET", body=None,
                   headers=None, timeout=15):
    """Call the iLink Bot API and return parsed JSON.

    Raises RuntimeError with a user-facing message on any failure so
    the HTTP handler can surface it cleanly. Tries certifi-backed TLS
    first to dodge broken system trust stores on locked-down machines.
    """
    import ssl
    base = (base_url or ILINK_DEFAULT_BASE).rstrip("/")
    url = base + path
    req_headers = {"User-Agent": "HermesPortable/iLink",
                   "iLink-App-ClientVersion": "1"}
    if headers:
        req_headers.update(headers)
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=req_headers,
                                 method=method)

    contexts = []
    try:
        import certifi  # type: ignore
        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    contexts.append(None)

    last_err = None
    for ctx in contexts:
        try:
            kwargs = {"timeout": timeout}
            if ctx is not None:
                kwargs["context"] = ctx
            with urllib.request.urlopen(req, **kwargs) as resp:
                payload = resp.read(2 * 1024 * 1024)
                if resp.status != 200:
                    raise RuntimeError(
                        f"iLink API returned HTTP {resp.status}: "
                        f"{payload[:200].decode('utf-8', errors='replace')}")
                try:
                    return json.loads(payload.decode("utf-8"))
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"iLink response was not JSON: {e}")
        except urllib.error.HTTPError as e:
            text = ""
            try:
                text = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise RuntimeError(f"iLink API HTTP {e.code}: {text}")
        except urllib.error.URLError as e:
            last_err = RuntimeError(f"iLink API unreachable: {e.reason}")
            # SSL failures are the main reason we have multiple contexts;
            # try the next one. Other URLErrors (DNS, connection refused)
            # also benefit from the retry — cheap.
            continue
        except (TimeoutError, OSError) as e:
            last_err = RuntimeError(f"iLink API timed out: {e}")
            continue
    raise last_err or RuntimeError("iLink API request failed")


def _ilink_fetch_qr(base_url=None):
    """Ask iLink for a fresh QR. Returns the parsed response with
    fields {qrcode, qrcode_img_content, ...}."""
    return _ilink_request(
        f"/ilink/bot/get_bot_qrcode?bot_type={ILINK_BOT_TYPE}",
        base_url=base_url,
    )


def _ilink_poll_qr(qrcode_token, base_url=None):
    """Long-poll iLink for QR status. The server holds the request for
    ~35s. Treat client-side timeouts as 'still waiting' so the UI keeps
    polling rather than seeing an error."""
    import urllib.parse as _uparse
    try:
        return _ilink_request(
            "/ilink/bot/get_qrcode_status?qrcode="
            + _uparse.quote(qrcode_token),
            base_url=base_url, timeout=ILINK_QR_POLL_TIMEOUT_SEC,
        )
    except RuntimeError as e:
        if "timed out" in str(e).lower():
            return {"status": "wait"}
        raise


def _qr_data_url(content):
    """Render a QR PNG as a data URL.

    Prefers the optional `qrcode` library when present (zero network),
    falls back to api.qrserver.com (free, no key, public). If both fail,
    returns an empty string and lets the frontend render the raw token
    so the user can copy-paste into any QR app.
    """
    if not isinstance(content, str) or not content:
        raise RuntimeError("QR content is empty")
    try:
        import io as _io
        import base64 as _b64
        import qrcode as _qr  # type: ignore
        img = _qr.make(content)
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return ("data:image/png;base64,"
                + _b64.b64encode(buf.getvalue()).decode("ascii"))
    except Exception:
        pass
    try:
        import base64 as _b64
        import urllib.parse as _uparse
        url = ("https://api.qrserver.com/v1/create-qr-code/"
               "?size=300x300&margin=10&data="
               + _uparse.quote(content, safe=""))
        with urllib.request.urlopen(url, timeout=10) as resp:
            png = resp.read(512 * 1024)
            return ("data:image/png;base64,"
                    + _b64.b64encode(png).decode("ascii"))
    except Exception:
        return ""


def _persist_wechat_credentials(account_id, token, base_url=None):
    """Write WEIXIN_* keys into data/.env so hermes' Weixin adapter
    picks them up at startup. Reuses parse_env to preserve other keys.
    Note: this writes a flat KEY=VALUE list; save_config() will rewrite
    with section headers on the next UI save, restoring the canonical
    format."""
    keys = parse_env()
    keys["WEIXIN_ACCOUNT_ID"] = _sanitize_env_value(account_id)
    keys["WEIXIN_TOKEN"] = _sanitize_env_value(token)
    if base_url:
        keys["WEIXIN_BASE_URL"] = _sanitize_env_value(base_url)
    lines = ["# Hermes Portable .env (auto-updated by WeChat QR login)"]
    for k, v in keys.items():
        if v:
            lines.append(f"{k}={v}")
        else:
            lines.append(f"# {k}=")
    _atomic_write_text(ENV_FILE, "\n".join(lines) + "\n", encoding="utf-8")


def wechat_start_login():
    """Kick off a new QR login session. Returns dict with
    {session, qr_data_url, qr_content, expires_in}.

    Refuses to start if too many sessions are already in flight. This
    is a localhost-only API but everyone on localhost can hit it, so a
    cap protects against accidental and intentional resource leaks.
    """
    import secrets
    # Cap check FIRST — before we hit the iLink API. We don't want to
    # burn upstream quota on requests we're going to refuse anyway.
    with _wechat_lock:
        _wechat_cleanup_expired_locked()
        if len(_wechat_logins) >= ILINK_MAX_ACTIVE_LOGINS:
            raise RuntimeError(
                f"Too many WeChat QR sessions in flight "
                f"({len(_wechat_logins)}); wait for them to expire "
                f"or call /api/wechat/cancel."
            )
    qr = _ilink_fetch_qr()
    qrcode_token = qr.get("qrcode")
    img_content = qr.get("qrcode_img_content") or qrcode_token
    if not qrcode_token or not img_content:
        raise RuntimeError("iLink did not return a QR code")
    session = secrets.token_urlsafe(16)
    data_url = _qr_data_url(img_content)
    with _wechat_lock:
        # Re-run cleanup + recheck the cap because we released the lock
        # while talking to iLink.
        _wechat_cleanup_expired_locked()
        if len(_wechat_logins) >= ILINK_MAX_ACTIVE_LOGINS:
            raise RuntimeError(
                f"Too many WeChat QR sessions in flight (recheck); "
                f"another caller filled the slots while we were "
                f"fetching the QR. Try again."
            )
        _wechat_logins[session] = {
            "qrcode": qrcode_token,
            "qr_data_url": data_url,
            "qr_content": img_content,
            "started_at": time.time(),
            "base_url": ILINK_DEFAULT_BASE,
            "refresh_count": 0,
        }
    return {
        "session": session,
        "qr_data_url": data_url,
        "qr_content": img_content,
        "expires_in": ILINK_LOGIN_TTL_SEC,
    }


def wechat_check_status(session):
    """Poll the iLink server for QR status. Persists creds and returns
    {status: 'confirmed', account_id, ...} when the user confirms on
    the phone, {status: 'refreshed', qr_data_url, ...} when iLink
    rotated the QR, or {status: 'wait'} otherwise."""
    with _wechat_lock:
        _wechat_cleanup_expired_locked()
        login = _wechat_logins.get(session)
        if not login:
            return {"status": "expired", "message": "No active session"}
        # Snapshot what we need OUTSIDE the lock so the 35s long-poll
        # doesn't block other UI threads.
        qrcode_token = login["qrcode"]
        base_url = login.get("base_url") or ILINK_DEFAULT_BASE
    try:
        result = _ilink_poll_qr(qrcode_token, base_url=base_url)
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    status = (result or {}).get("status", "wait")
    if status == "expired":
        with _wechat_lock:
            login = _wechat_logins.get(session)
            if not login:
                return {"status": "expired", "message": "session gone"}
            login["refresh_count"] = login.get("refresh_count", 0) + 1
            if login["refresh_count"] > ILINK_MAX_QR_REFRESH:
                _wechat_logins.pop(session, None)
                return {"status": "expired",
                        "message": "QR expired too many times"}
        try:
            new_qr = _ilink_fetch_qr(base_url=base_url)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}
        new_token = new_qr.get("qrcode")
        new_content = new_qr.get("qrcode_img_content") or new_token
        if not new_token:
            return {"status": "error", "message": "iLink refused refresh"}
        new_data_url = _qr_data_url(new_content)
        with _wechat_lock:
            login = _wechat_logins.get(session)
            if not login:
                return {"status": "expired", "message": "session gone"}
            login["qrcode"] = new_token
            login["qr_data_url"] = new_data_url
            login["qr_content"] = new_content
            login["started_at"] = time.time()
        return {
            "status": "refreshed",
            "qr_data_url": new_data_url,
            "qr_content": new_content,
        }
    if status == "confirmed":
        bot_id = result.get("ilink_bot_id") or ""
        bot_token = result.get("bot_token") or ""
        srv_base = result.get("baseurl") or base_url
        if not bot_id or not bot_token:
            return {"status": "error",
                    "message": "Server did not return credentials"}
        # Persist BEFORE removing the session so a flaky disk write
        # leaves the user able to retry the same QR (which iLink
        # already considers consumed — but at least the UI flow is
        # consistent and we surface the disk error clearly).
        try:
            _persist_wechat_credentials(bot_id, bot_token, base_url=srv_base)
        except Exception as e:
            return {"status": "error",
                    "message": f"Failed to save credentials: {e}"}
        with _wechat_lock:
            _wechat_logins.pop(session, None)
        return {
            "status": "confirmed",
            "account_id": bot_id,
            "base_url": srv_base,
            "message": "WeChat 登录成功，凭据已保存到 data/.env",
        }
    # scanned / wait / unknown — pass through
    return {"status": status}


def wechat_cancel_login(session=None):
    """Drop a pending session (or all of them)."""
    with _wechat_lock:
        if session:
            _wechat_logins.pop(session, None)
        else:
            _wechat_logins.clear()


# ═══════════════════════════════════════════════════════════════
#  HTML — matching Hermes Web UI style (port 9119)
# ═══════════════════════════════════════════════════════════════

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Portable — 配置</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='18' fill='%23041c1c'/%3E%3Cg fill='none' stroke='%23ffe6cb' stroke-width='4.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M 28 32 L 42 60 M 56 32 L 42 60 L 36 78'/%3E%3Cpath d='M 64 32 L 64 60 Q 64 72 76 72 L 76 32'/%3E%3C/g%3E%3C/svg%3E">
<meta name="theme-color" content="#edff45" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#edff45" media="(prefers-color-scheme: light)">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
  /* Google Fonts removed for China compatibility */

  :root {
    /* yu.ai v2 Design System */
    --bg-base: 23 13 2;
    --mid-base: 245 240 232;
    --dim-base: 170 166 158;
    --accent-base: 237 255 69;
    --warn-base: 255 189 56;
    --danger-base: 255 138 107;
    
    --bg: rgb(var(--bg-base));
    --mid: rgb(var(--mid-base));
    --dim: rgb(var(--dim-base));
    --accent: rgb(var(--accent-base));
    --warn: rgb(var(--warn-base));
    --danger: rgb(var(--danger-base));
    
    --border: rgb(var(--mid-base) / .12);
    --border-strong: rgb(var(--mid-base) / .24);
    --hover: rgb(var(--mid-base) / .05);
    --hover-strong: rgb(var(--mid-base) / .08);
    
    --fg: var(--mid);
    --fg-muted: var(--dim);
    --card: var(--bg);
    --secondary: var(--bg);
    --muted: var(--border);
    --accent: var(--accent);
    --emerald: var(--accent);
    --emerald-dim: var(--accent);
    --warning: var(--warn);
    --success: var(--accent);
    --destructive: var(--danger);
    
    --font-sans: system-ui, -apple-system, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    --font-serif: 'LXGW WenKai', Georgia, 'Noto Serif SC', 'Source Han Serif SC', serif;
    --font-mono: 'Courier New', 'Menlo', monospace;
  }
  [data-theme="light"] {
    --bg-base: 245 245 245;
    --mid-base: 23 13 2;
    --dim-base: 80 70 60;
    --accent-base: 0 0 200;
    --border: rgb(var(--mid-base) / .18);
    --border-strong: rgb(var(--mid-base) / .3);
    --hover: rgb(var(--mid-base) / .06);
    --hover-strong: rgb(var(--mid-base) / .1);
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) {
      --bg-base: 245 245 245;
      --mid-base: 23 13 2;
      --dim-base: 80 70 60;
      --accent-base: 0 0 200;
      --border: rgb(var(--mid-base) / .18);
      --border-strong: rgb(var(--mid-base) / .3);
      --hover: rgb(var(--mid-base) / .04);
      --hover-strong: rgb(var(--mid-base) / .07);
    }
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  /* yu.ai background layers */
  .bg-i { position: fixed; inset: 0; z-index: 0; pointer-events: none; }
  .bg-i img {
    width: 100vw; height: 100vh; object-fit: cover;
    opacity: 0.06; filter: grayscale(1) brightness(0.7);
    object-position: center bottom;
  }
  .bg-n {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    mix-blend-mode: color-dodge; opacity: 0.03;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' fill='%23eaeaea' filter='url(%23n)' opacity='.6'/%3E%3C/svg%3E");
    background-size: 512px 512px;
  }
  .bg-g {
    position: fixed; inset: 0; z-index: 300; pointer-events: none;
    mix-blend-mode: lighten; opacity: 0.15;
    background: radial-gradient(ellipse at 0% 0%, rgba(255,189,56,0.25) 0%, transparent 50%);
  }
  [data-theme="light"] .bg-i img { opacity: 0.04; filter: grayscale(1) brightness(1.5); }
  [data-theme="light"] .bg-n { opacity: 0.015; }
  [data-theme="light"] .bg-g { opacity: 0.06; }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) .bg-i img { opacity: 0.04; filter: grayscale(1) brightness(1.5); }
    :root:not([data-theme="dark"]) .bg-n { opacity: 0.015; }
    :root:not([data-theme="dark"]) .bg-g { opacity: 0.06; }
  }


  body {
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--fg);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    scrollbar-color: #f5f5f533 transparent;
    position: relative;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* warm glow overlay (official style) */
  body::before {
    content: '';
    position: fixed; inset: 0;
    pointer-events: none; z-index: 99;
    mix-blend-mode: lighten;
    opacity: 0.22;
    background: radial-gradient(ellipse at 0% 0%, rgba(255,189,56,0) 60%, rgba(255,189,56,0.35) 100%);
  }
  /* grain overlay */
  body::after {
    content: '';
    position: fixed; inset: 0;
    pointer-events: none; z-index: 100;
    mix-blend-mode: color-dodge;
    opacity: 0.1;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' fill='%23eaeaea' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E");
    background-size: 512px 512px;
  }

  .container {
    max-width: 640px;
    margin: 0 auto;
    padding: 32px 16px 48px;
    position: relative;
    z-index: 1;
  }

  /* Header */
  .header {
    text-align: center;
    padding: 24px 0 20px;
  }
  .header .logo {
    display: inline-block;
    width: 72px;
    height: 72px;
    margin-bottom: 12px;
    filter: drop-shadow(0 0 12px rgba(255, 230, 203, 0.15));
    transition: transform 0.4s ease;
  }
  .header .logo:hover {
    transform: scale(1.08) rotate(-3deg);
  }
  .header h1 {
    font-family: var(--font-sans);
    font-size: 28px;
    font-weight: 400;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--fg);
  }
  .header .subtitle {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg-muted);
    letter-spacing: 0.08em;
    margin-top: 4px;
  }

  /* Section labels like 9119 */
  .section-label {
    font-family: var(--font-sans);
    font-size: 12px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--fg-muted);
    margin-bottom: 8px;
    padding-left: 2px;
    mix-blend-mode: plus-lighter;
  }

  /* Card */
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
  }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 2px;
    margin-bottom: 16px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 3px;
  }
  .tab {
    flex: 1;
    padding: 8px 0;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.05em;
    cursor: pointer;
    border: none;
    background: transparent;
    color: var(--fg-muted);
    border-radius: 6px;
    transition: all 0.15s;
  }
  .tab:hover { color: var(--fg); background: var(--secondary); }
  .tab.active {
    background: var(--secondary);
    color: var(--fg);
    font-weight: 700;
  }

  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* Provider grid */
  .provider-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
    margin-bottom: 12px;
  }
  .provider-btn {
    padding: 8px 4px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--fg-muted);
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.05em;
    cursor: pointer;
    text-align: center;
    transition: all 0.15s;
  }
  .provider-btn { text-transform: none; letter-spacing: 0; }
  .provider-btn:hover { border-color: var(--fg); color: var(--fg); }
  .provider-btn.active {
    border-color: var(--emerald-dim);
    color: var(--emerald);
    background: oklch(0.18 0.02 170);
  }

  /* Form elements */
  label {
    display: block;
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--fg-muted);
    margin-bottom: 4px;
  }
  input[type="text"], input[type="password"], input[type="number"], select {
    width: 100%;
    padding: 8px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--fg);
    font-family: var(--font-mono);
    font-size: 12px;
    outline: none;
    transition: border-color 0.15s;
  }
  input, select, textarea { text-transform: none; letter-spacing: normal; }
  input:focus, select:focus { border-color: var(--fg); }
  select { cursor: pointer; }
  select option { background: var(--bg); color: var(--fg); }

  .field { margin-bottom: 10px; }
  .field:last-child { margin-bottom: 0; }
  .row { display: flex; gap: 8px; }
  .row .field { flex: 1; }

  /* API key row */
  .api-key-row { display: flex; gap: 8px; align-items: center; }
  .api-key-row input { flex: 1; }
  .api-status {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--border); flex-shrink: 0;
    transition: background 0.15s;
  }
  .api-status.set { background: var(--emerald); }

  /* Toggle switch */
  .toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .toggle-row:last-child { border-bottom: none; }
  .toggle-info { flex: 1; }
  .toggle-label {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg);
  }
  .toggle-desc {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg-muted);
    margin-top: 2px;
  }
  .switch {
    position: relative;
    width: 36px; height: 18px;
    flex-shrink: 0;
    margin-left: 12px;
  }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; cursor: pointer; inset: 0;
    background: var(--muted);
    border-radius: 18px;
    border: 1px solid var(--border);
    transition: 0.2s;
  }
  .slider:before {
    content: "";
    position: absolute;
    height: 12px; width: 12px;
    left: 2px; bottom: 2px;
    background: var(--fg-muted);
    border-radius: 50%;
    transition: 0.2s;
  }
  .switch input:checked + .slider { background: var(--emerald-dim); border-color: var(--emerald); }
  .switch input:checked + .slider:before { transform: translateX(18px); background: var(--fg); }

  /* Channel cards */
  .channel-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 6px;
    transition: border-color 0.15s;
  }
  .channel-card.enabled { border-color: var(--emerald-dim); }
  .channel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
  }
  .channel-info { display: flex; align-items: center; gap: 10px; }
  .channel-icon {
    font-size: 14px;
    color: var(--fg-muted);
    width: 20px;
    text-align: center;
    font-family: var(--font-mono);
  }
  .channel-name {
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    color: var(--fg);
  }
  .channel-desc {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg-muted);
  }
  .channel-status {
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
  }
  .channel-status.on { background: oklch(0.765 0.177 163.223 / 0.1); color: var(--emerald); }
  .channel-status.off { background: var(--muted); color: var(--fg-muted); }
  .channel-right { display: flex; align-items: center; gap: 8px; }

  .channel-fields {
    margin-top: 12px;
    display: none;
  }
  .channel-fields.show { display: block; }

  /* Model preview */
  .model-preview {
    margin-top: 6px;
    padding: 6px 10px;
    background: var(--bg);
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--emerald);
    letter-spacing: 0.05em;
  }

  /* Actions */
  .actions {
    display: flex;
    gap: 8px;
    padding: 16px 0 24px;
  }
  .btn {
    flex: 1;
    padding: 10px 16px;
    border: 1px solid var(--border-strong, var(--border));
    border-radius: 6px;
    font-family: var(--font-sans);
    font-size: 13px;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: center;
    font-weight: 600;
    background: var(--hover);
    color: var(--mid);
    min-height: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--hover-strong, var(--hover));
  }
  .btn:active {
    transform: scale(0.97);
    background: var(--border);
  }
  .btn.destructive {
    color: var(--danger, #ff6b6b);
    border-color: var(--danger, #ff6b6b);
  }
  .btn.destructive:hover {
    background: var(--danger, #ff6b6b);
    color: var(--bg);
  }
  .btn-save {
    background: var(--secondary);
    color: var(--fg);
    border-color: var(--fg);
  }
  .btn-save:hover { background: oklch(0.18 0.02 170); }
  .btn-launch {
    background: var(--emerald-dim);
    color: var(--bg);
    border-color: var(--emerald);
  }
  .btn-launch:hover { background: var(--emerald); }
  .btn-launch:disabled {
    background: var(--muted);
    color: var(--fg-muted);
    border-color: var(--border);
    cursor: not-allowed;
  }

  /* Toast */
  .toast {
    position: fixed;
    top: 16px; right: 16px;
    padding: 10px 16px;
    border-radius: 6px;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
    transform: translateX(120%);
    transition: transform 0.2s ease;
    z-index: 200;
    border: 1px solid var(--border);
  }
  .toast.show { transform: translateX(0); }
  .toast.success { background: var(--secondary); color: var(--emerald); border-color: var(--emerald); }
  .toast.error { background: var(--secondary); color: var(--destructive); border-color: var(--destructive); }

  /* Footer */
  .footer {
    text-align: center;
    padding: 8px 0;
    font-family: var(--font-mono);
    font-size: 12px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--fg-muted);
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #f5f5f526; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #f5f5f540; }

  /* Selection */
  ::selection { background: var(--fg); color: var(--bg); }

  /* Onboarding overlay */
  .onboarding {
    position: fixed; inset: 0; z-index: 300;
    background: rgba(4,28,28,0.92);
    display: flex; align-items: center; justify-content: center;
    backdrop-filter: blur(8px);
  }
  .onboarding.hidden { display: none; }
  .onboarding-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 32px 28px;
    max-width: 420px; width: 90%;
    text-align: center;
  }
  .onboarding-card h2 {
    font-family: var(--font-sans);
    font-size: 22px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 12px;
  }
  .onboarding-card p {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg-muted);
    line-height: 1.6;
    margin-bottom: 8px;
    letter-spacing: 0.03em;
  }
  .onboarding-steps {
    text-align: left;
    margin: 16px 0;
    padding: 12px 16px;
    background: var(--bg);
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .onboarding-step {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 8px 0;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--fg-muted);
    letter-spacing: 0.03em;
  }
  .onboarding-step:last-child { border-bottom: none; }
  .step-num {
    width: 20px; height: 20px;
    border-radius: 50%;
    background: var(--secondary);
    border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; color: var(--emerald);
    flex-shrink: 0;
    margin-top: -1px;
  }
  .step-num.active {
    background: var(--emerald-dim);
    border-color: var(--emerald);
    color: var(--bg);
  }
  .onboarding-card .btn { margin-top: 8px; }


  
  /* ─────── Button Styles ─────── */


/* ─────── yu.ai aligned shell ─────── */
  .y-page { position: relative; z-index: 200; max-width: 1100px; margin: 0 auto; padding: 0; overflow-x: hidden; }
  .y-row { display: grid; grid-template-columns: 1fr; border-top: 1px solid var(--border); border-left: 1px solid var(--border); }
  .y-cell { padding: 16px; border-right: 1px solid var(--border); min-width: 0; display: flex; align-items: center; }
  .y-cell.s1 { grid-column: span 1; }
  .y-cell.s2 { grid-column: span 2; }
  .y-cell.s4 { grid-column: span 4; }
  .y-cell.s6 { grid-column: 1 / -1; }
  @media (min-width: 1024px) { .y-row.nav-row { grid-template-columns: 1fr 2fr 1fr 1fr 1fr; } }

  .y-label { font-size: 0.9375rem; letter-spacing: 0.1875rem; text-transform: uppercase; }
  .y-label-sm { font-size: 0.75rem; letter-spacing: 0.1875rem; text-transform: uppercase; }
  .y-label-xs { font-size: 0.6875rem; letter-spacing: 0.125rem; text-transform: uppercase; }
  .y-title { font-family: var(--font-serif); font-size: 2.625rem; font-weight: 700; line-height: 1; letter-spacing: 0.0525rem; }
  .y-display { font-family: var(--font-serif); font-size: 3.5rem; font-weight: 700; line-height: 1.1; letter-spacing: -0.02em; mix-blend-mode: plus-lighter; }
  .y-sub { font-size: 1.125rem; line-height: 1.6; opacity: 0.6; }
  .y-op-5 { opacity: 0.5; } .y-op-7 { opacity: 0.7; }

  @keyframes yblink { 0%,50% { opacity: 1; } 51%,100% { opacity: 0; } }
  .y-blink { display: inline-block; width: 1ch; height: 1.1em; background: currentColor; vertical-align: text-bottom; animation: yblink 1.2s step-end infinite; }
  @media (prefers-reduced-motion: reduce) { .y-blink { animation: none; opacity: 1; } }

  .y-nav-link { position: relative; display: flex; align-items: center; width: 100%; height: 100%; color: inherit; text-decoration: none; padding: 16px; cursor: pointer; }
  .y-nav-link .y-blink { display: none; }
  .y-nav-link:hover .y-blink, .y-nav-link:focus-visible .y-blink { display: inline-block; }
  .y-nav-link:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
  .y-nav-link::before { content: ""; position: absolute; inset: -12px; background: var(--fg); pointer-events: none; opacity: 0; transition: opacity 0.25s; z-index: -1; }
  .y-nav-link:hover::before { opacity: 0.1; }

  .y-hero { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 20px; padding: 60px 20px 44px; width: 100%; }
  .y-term { width: 100%; max-width: 560px; border: 4px double var(--border); }
  .y-term-h { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--border); }
  .y-td { width: 10px; height: 10px; border-radius: 50%; }
  .y-td:nth-child(1) { background: var(--fg); }
  .y-td:nth-child(2) { background: var(--fg); opacity: 0.6; }
  .y-td:nth-child(3) { background: var(--fg); opacity: 0.5; }
  .y-term-label { margin-left: auto; font-family: var(--font-mono); font-size: 0.6875rem; letter-spacing: 0.1875rem; opacity: 0.5; }
  .y-term-b { font-family: var(--font-mono); font-size: 0.78rem; line-height: 1.85; padding: 18px 16px; white-space: pre-wrap; min-height: 100px; word-break: break-word; text-align: left; }
  .y-term-b .p { color: var(--accent); }
  .y-term-b .t { opacity: 0.6; }

  .y-footer { display: grid; grid-template-columns: 1fr; border-top: 1px solid var(--border); border-left: 1px solid var(--border); border-bottom: 1px solid var(--border); margin-top: 28px; }
  .y-footer .c { padding: 16px; border-right: 1px solid var(--border); display: flex; align-items: center; }
  @media (min-width: 1024px) { .y-footer { grid-template-columns: 1fr 1fr 1fr 1fr 1fr; } }

  .y-theme-toggle { background: none; border: none; cursor: pointer; color: var(--fg); opacity: 0.5; padding: 8px; line-height: 0; transition: opacity 0.2s; display: flex; align-items: center; border-radius: 4px; }
  .y-theme-toggle:hover, .y-theme-toggle:focus-visible { opacity: 1; outline: 1px solid var(--border); }
  .y-theme-toggle svg { display: block; }

  @media (max-width: 1023px) {
    .y-row, .y-row.nav-row { grid-template-columns: 1fr; border-left: none; }
    .y-cell { border-right: none; }
    .y-footer { grid-template-columns: 1fr; border-left: none; }
    .y-footer .c { border-right: none; }
  }
  @media (max-width: 768px) {
    .y-display { font-size: 2.2rem; }
    .y-sub { font-size: 0.95rem; }
    .y-hero { padding: 40px 16px 28px; }
    .y-term-b { font-size: 0.72rem; padding: 14px 12px; }
  }
  @media (max-width: 640px) {
    .y-display { font-size: 1.8rem; }
    .y-hero { padding: 32px 12px 20px; }
  }


  /* ─────── yu.ai-aligned re-skin of functional widgets ─────── */
  .container { max-width: none; padding: 0 24px 28px; }

  .container > .header,
  .container > .header > * { background: transparent; border: none; }
  .container > .header { padding: 16px 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin: 0 0 0 0; }

  /* Tabs — flat row, accent on active */
  .tabs {
    gap: 0;
    border: 1px solid var(--border);
    margin: 24px 0 0;
  }
  .tab {
    background: transparent;
    border: none;
    border-right: 1px solid var(--border);
    border-radius: 0;
    padding: 14px 22px;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--fg-muted);
    cursor: pointer;
    transition: color 0.2s, background 0.2s;
  }
  .tabs > .tab:last-child { border-right: none; }
  .tab:hover { color: var(--fg); }
  .tab.active {
    color: var(--accent);
    background: rgba(237,255,69,0.04);
  }

  .tab-panel { padding: 24px 0; }
  .tab-panel h2, .tab-panel h3 {
    font-family: var(--font-serif);
    font-weight: 700;
    color: var(--fg);
    mix-blend-mode: plus-lighter;
    letter-spacing: -0.005em;
  }
  .section-label {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--fg-muted);
  }

  /* Provider grid — flatter buttons */
  .provider-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0;
    border: 1px solid var(--border);
  }
  .provider-btn {
    background: transparent;
    border: none;
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    border-radius: 0;
    padding: 16px 14px;
    text-align: left;
    cursor: pointer;
    font-family: var(--font-serif);
    color: var(--fg);
    transition: background 0.2s, color 0.2s;
  }
  .provider-btn:hover {
    background: rgba(245,240,232,0.04);
  }
  .provider-btn.active {
    background: rgba(237,255,69,0.06);
    color: var(--accent);
  }

  /* Channel cards — flat */
  .channel-card {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 0;
    transition: border-color 0.2s, background 0.2s;
  }
  .channel-card:hover {
    border-color: var(--accent);
    background: rgba(245,240,232,0.02);
  }
  .channel-name {
    font-family: var(--font-serif);
    font-weight: 600;
  }
  .channel-desc {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    opacity: 0.55;
  }
  .channel-status { font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.1em; }

  /* Buttons */
  .btn, .btn-save, .btn-launch {
    border-radius: 0;
    font-family: var(--font-mono);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .btn-launch, .btn-save {
    border: 1px solid var(--accent);
    color: var(--accent);
    background: transparent;
    padding: 12px 24px;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .btn-launch:hover, .btn-save:hover {
    background: var(--accent);
    color: var(--bg);
  }
  .btn-launch:disabled, .btn-save:disabled {
    border-color: var(--border);
    color: var(--fg-muted);
    cursor: not-allowed;
    opacity: 0.5;
  }

  /* Inputs / selects */
  .field input, .field select, .field textarea, .api-key-row input {
    border-radius: 0;
    font-family: var(--font-mono);
    background: transparent;
  }

  /* Switch (toggle) — keep functional shape but recolor */
  .switch input:checked + .slider { background-color: var(--accent); }

  /* Toggle rows — flatter */
  .toggle-row {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 0;
  }
  .toggle-label {
    font-family: var(--font-serif);
    font-weight: 600;
  }
  .toggle-desc {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    opacity: 0.6;
  }

  /* Onboarding card — yu.ai-styled */
  .onboarding-card {
    border: 1px solid var(--border);
    border-radius: 0;
    background: var(--card);
  }
  .onboarding-card h2 {
    font-family: var(--font-serif);
    font-weight: 700;
    mix-blend-mode: plus-lighter;
  }
  .onboarding-step {
    border-radius: 0;
  }
  .step-num {
    border-radius: 50%;
    font-family: var(--font-mono);
  }

  /* Toast */
  .toast { border-radius: 0; font-family: var(--font-mono); letter-spacing: 0.05em; }

  /* Card class generic */
  .card {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 0;
  }

  /* Fields */
  .field { margin-bottom: 14px; }
  .field label, .field > strong {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    opacity: 0.6;
  }

  /* Footer — keep yu.ai version added earlier; make sure it sits below */
  .footer { display: none; }  /* hide any inherited Hermes footer; y-footer is the canonical one */



  /* ─────── flatten remaining dark fills (yu.ai aesthetic) ─────── */
  [style*="background:var(--secondary)"],
  [style*="background: var(--secondary)"],
  [style*="background:var(--card)"],
  [style*="background: var(--card)"],
  [style*="background:var(--muted)"],
  [style*="background: var(--muted)"] {
    background: transparent;
  }

  /* CSS-rule level: any block that uses --card / --secondary / --muted
     for its fill becomes transparent. We can't selector-match a CSS
     property value, so we override the most common offenders by
     class name. */
  .api-key-row, .channel-fields, .field {
    background: transparent;
  }

  /* Inputs / selects transparent */
  .container input,
  .container select,
  .container textarea {
    background: transparent;
    border-color: var(--border);
    border-radius: 0;
    font-family: var(--font-mono);
  }
  .container input:focus,
  .container select:focus,
  .container textarea:focus {
    border-color: var(--accent);
    outline: none;
  }

  /* Toast — flat with accent border */
  .toast {
    background: var(--bg);
    border: 1px solid var(--accent);
    border-radius: 0;
    font-family: var(--font-mono);
    letter-spacing: 0.05em;
  }


.skip-link{position:absolute;top:-40px;left:0;background:var(--accent);color:var(--bg);padding:8px 16px;z-index:1000;transition:top .3s;font-family:var(--font-sans);font-size:13px}
.skip-link:focus{top:0}
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/lxgw-wenkai-webfont@1.7.0/style.css" crossorigin />
<style>
  /* LXGW WenKai fallback for offline */
  @font-face {
    font-family: 'LXGW WenKai';
    src: local('LXGW WenKai'), local('LXGWWenKai-Regular');
    font-display: swap;
  }
</style>
</head>
<body>
<a href="#main" class="skip-link">跳到主要内容</a>
<div class="bg-i" aria-hidden="true"><img alt="" src="https://yuai-r.cn/egret-ink.jpg" width="1920" height="1080" loading="lazy" decoding="async" onerror="this.parentNode.style.display='none'"></div>
<div class="bg-n" aria-hidden="true"></div>
<div class="bg-g" aria-hidden="true"></div>
<div class="onboarding" id="onboarding" style="display:none">
  <div class="onboarding-card">
    <h2>Hermes Portable</h2>
    <p>欢迎使用！完成以下步骤即可开始：</p>
    <div class="onboarding-steps">
      <div class="onboarding-step">
        <div class="step-num active" id="step1">1</div>
        <div>选择一个 LLM 提供商，填入 API Key</div>
      </div>
      <div class="onboarding-step">
        <div class="step-num" id="step2">2</div>
        <div>点击「测试连接」确认 Key 有效</div>
      </div>
      <div class="onboarding-step">
        <div class="step-num" id="step3">3</div>
        <div>选择模型 → 保存 → 启动</div>
      </div>
    </div>
    <p style="opacity:0.6">API Key 仅存储在本机 data/.env 中</p>
    <button class="btn primary btn-launch" style="width:100%;margin-top:12px" onclick="dismissOnboarding()">
      开始配置
    </button>
  </div>
</div>

<main class="y-page" role="main" id="main">

<nav class="y-row nav-row" aria-label="Primary">
  <div class="y-cell s2"><a href="https://yuai-r.cn/" class="y-title" style="text-decoration:none;color:inherit">yu.ai</a></div>
  <div class="y-cell s2" style="padding:0">
    <a class="y-nav-link" href="https://yuai-r.cn/"><span class="y-label">hermes config</span></a>
  </div>
  <div class="y-cell" style="justify-content:flex-end;gap:8px">
    <button id="webui-btn" class="btn" onclick="toggleWebUI()" style="font-size:11px;padding:4px 8px;">Web UI</button>
    <button id="y-theme-btn" aria-label="切换主题" class="y-theme-toggle" type="button"><svg class="y-theme-sun" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg><svg class="y-theme-moon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="display:none" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
  </div>
</nav>

<div class="y-row">
  <div class="y-cell s6" style="border-right:none;padding:0">
    <div class="y-hero">
      <span class="y-label-xs y-op-7" style="letter-spacing:.15rem">hermes portable · config</span>
      <h1 class="y-display">hermes</h1>
      <p class="y-sub">成长型 AI 智能体 · 持久记忆 · 跨平台网关</p>
      <div class="y-term" aria-hidden="true">
        <div class="y-term-h">
          <span class="y-td"></span><span class="y-td"></span><span class="y-td"></span>
          <span class="y-term-label">hermes</span>
        </div>
        <div class="y-term-b" id="liveTerm"><span class="p">$ ./hermes serve</span>
<span class="t" id="liveStatusLine">  · checking hermes…</span>
<span class="y-blink"></span></div>
      </div>
    </div>
  </div>
</div>

<div class="container">
  <div class="header">
    <div id="hermesStatus" style="margin-top:12px;display:none;align-items:center;justify-content:center;gap:8px;font-family:var(--font-mono);font-size:11px;color:var(--fg-muted);">
      <span id="statusDot" style="width:8px;height:8px;border-radius:50%;background:#666;display:inline-block;"></span>
      <span id="statusText">检测中...</span>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('model',this)">模型</button>
    <button class="tab" onclick="switchTab('channels',this)">渠道</button>
    <button class="tab" onclick="switchTab('settings',this)">设置</button>
  </div>

  <form id="configForm">

    <!-- TAB: Model -->
    <div id="tab-model" class="tab-panel active">
      <div class="section-label">API 密钥</div>
      <div class="card">
        <div class="provider-grid" id="providerGrid"></div>
        <div id="apiKeySection"></div>
      </div>

      <div class="section-label" style="margin-top:12px">模型</div>
      <div class="card">
        <div class="field">
          <label>默认模型</label>
          <select id="modelSelect"></select>
          <div class="model-preview" id="modelPreview">current: —</div>
          <div id="catalogStatus" style="margin-top:4px;font-family:var(--font-mono);font-size:9px;color:var(--fg-muted,#9a968e);letter-spacing:0.04em;display:none"></div>
        </div>
        <div class="row" style="margin-top:10px">
          <div class="field">
            <label>最大轮数</label>
            <input type="number" id="maxTurns" value="90" min="10" max="500">
          </div>
          <div class="field">
            <label>超时 (秒)</label>
            <input type="number" id="timeout" value="180" min="30" max="600">
          </div>
        </div>
      </div>
    </div>

    <!-- TAB: Channels -->
    <div id="tab-channels" class="tab-panel">
      <div class="section-label">消息渠道</div>
      <div class="card">
        <p style="font-family:var(--font-mono);font-size:10px;color:var(--fg-muted);margin-bottom:12px;letter-spacing:0.05em;">
          启用渠道后，Hermes 可通过对应平台收发消息。
        </p>
        <div id="channelList"></div>
      </div>
    </div>

    <!-- TAB: Settings -->
    <div id="tab-settings" class="tab-panel">
      <div class="section-label">偏好设置</div>
      <div class="card">
        <div class="toggle-row">
          <div class="toggle-info">
            <div class="toggle-label">上下文压缩</div>
            <div class="toggle-desc">自动压缩长对话以节省 token</div>
          </div>
          <label class="switch"><input type="checkbox" id="compression" checked><span class="slider"></span></label>
        </div>
        <div class="toggle-row">
          <div class="toggle-info">
            <div class="toggle-label">显示费用</div>
            <div class="toggle-desc">每次回复显示 token 用量和费用</div>
          </div>
          <label class="switch"><input type="checkbox" id="showCost" checked><span class="slider"></span></label>
        </div>
        <div class="toggle-row">
          <div class="toggle-info">
            <div class="toggle-label">工具进度</div>
            <div class="toggle-desc">实时显示工具调用进度</div>
          </div>
          <label class="switch"><input type="checkbox" id="showToolProgress" checked><span class="slider"></span></label>
        </div>
        <div class="toggle-row">
          <div class="toggle-info">
            <div class="toggle-label">持久记忆</div>
            <div class="toggle-desc">跨会话记住你的偏好设置</div>
          </div>
          <label class="switch"><input type="checkbox" id="memoryEnabled" checked><span class="slider"></span></label>
        </div>
      </div>
      <div class="section-label" style="margin-top:12px">版本更新</div>
      <div class="card">
        <div id="versionInfo" style="font-family:var(--font-mono);font-size:11px;color:var(--fg-muted);">
          正在检查版本...
        </div>
        <div style="margin-top:10px">
          <button type="button" class="btn btn-save" style="width:100%" onclick="checkUpdate()">
            检查更新
          </button>
        </div>
        <div id="updateAction" style="margin-top:8px;display:none">
          <button type="button" class="btn primary btn-launch" style="width:100%" onclick="runUpdate()">
            更新到最新版
          </button>
        </div>
        <div id="updateLog" style="margin-top:8px;font-family:var(--font-mono);font-size:10px;color:var(--emerald);display:none;white-space:pre-wrap;"></div>
      </div>

      <div class="section-label" style="margin-top:12px">配置管理</div>
      <div class="card">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="btn" style="flex:1;min-width:120px" onclick="exportConfig()">导出配置</button>
          <button type="button" class="btn" style="flex:1;min-width:120px" onclick="startImport()">导入配置</button>
          <button type="button" class="btn" style="flex:1;min-width:120px" onclick="viewEnv()">查看 .env</button>
          <button type="button" class="btn destructive" style="flex:1;min-width:120px" onclick="resetConfig()">重置</button>
        </div>
        <input type="file" id="importFileInput" accept=".json" style="display:none" onchange="doImport(event)">
      </div>

      <div class="section-label" style="margin-top:12px">运行日志</div>
      <div class="card">
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <button type="button" class="btn" style="flex:1" onclick="refreshLogs()">刷新日志</button>
          <button type="button" class="btn" style="flex:1" onclick="clearLogView()">清空显示</button>
        </div>
        <pre id="logContent" style="background:#170d02;color:#f5f5f5;padding:12px;border-radius:8px;font-family:var(--font-mono);font-size:11px;line-height:1.6;max-height:280px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;">点击「刷新日志」查看最近 200 行</pre>
      </div>
    </div>

    <div class="actions">
      <button type="button" class="btn btn-save" onclick="saveConfig()">保存</button>
      <button type="button" class="btn" id="restartBtn" onclick="restartHermes()" style="display:none">重启 Hermes</button>
      <button type="button" class="btn primary btn-launch" id="launchBtn" onclick="launchHermes()">启动</button>
    </div>
  </form>

  <div class="footer">Hermes Portable · 数据存储在 data/</div>
</div>

<div class="toast" id="toast"></div>

<script>
const PROVIDERS = __PROVIDERS__;
const CHANNELS  = __CHANNELS__;
let activeProvider = '__ACTIVE_PROVIDER__';
let currentEnv = __CURRENT_ENV__;
let enabledChannels = __ENABLED_CHANNELS__;
let savedOnce = false;
let isFirstRun = __FIRST_RUN__;

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

// Onboarding
function showOnboarding() {
  document.getElementById('onboarding').style.display = 'flex';
}
function dismissOnboarding() {
  document.getElementById('onboarding').style.display = 'none';
}
function updateStep(step) {
  for (let i = 1; i <= 3; i++) {
    const el = document.getElementById('step' + i);
    if (el) {
      el.classList.toggle('active', i <= step);
    }
  }
}

function init() {
  renderProviders();
  renderApiKeySection();
  updateModelSelect();
  renderChannels();
  restoreConfig();
  // First run: show onboarding, disable launch
  if (isFirstRun) {
    showOnboarding();
    document.getElementById('launchBtn').disabled = true;
  }
}

function renderProviders() {
  const iconMap = {custom:'openrouter',nous:'nousresearch'};
  const g = document.getElementById('providerGrid');
  g.innerHTML = PROVIDERS.map(p => {
    const iconName = iconMap[p.id] || p.id;
    const icon = `<img src="/icons/${iconName}.svg" width="16" height="16" alt="" style="border-radius:3px;vertical-align:middle;margin-right:4px;" onerror="this.style.display='none'">`;
    return `<button type="button" class="provider-btn ${p.id===activeProvider?'active':''}"
            onclick="selectProvider('${p.id}')">${icon}${p.name}</button>`;
  }).join('');
}

function selectProvider(id) { activeProvider = id; renderProviders(); renderApiKeySection(); updateModelSelect(); }

function renderApiKeySection() {
  const s = document.getElementById('apiKeySection');
  const p = PROVIDERS.find(x => x.id === activeProvider);
  if (!p) return;
  const hasKey = currentEnv[p.env] && currentEnv[p.env].length > 0;
  s.innerHTML = `<div class="field">
    <label>${p.name} API Key</label>
    <div class="api-key-row">
      <input type="password" id="apiKey_${p.env}" placeholder="粘贴你的 ${p.name} API Key"
             value="${hasKey ? escapeHtml(currentEnv[p.env]) : ''}" oninput="updateKeyStatus(this,'${p.env}')">
      <div class="api-status ${hasKey?'set':''}" id="status_${p.env}"></div>
    </div></div>
    <div style="margin-top:8px">
      <button type="button" class="btn btn-save" style="width:100%;padding:8px;font-size:10px" onclick="testConnection()">
        测试连接
      </button>
      <div id="testResult" style="margin-top:6px;font-family:var(--font-mono);font-size:10px;display:none"></div>
    </div>`;
}

function updateKeyStatus(input, envKey) {
  const st = document.getElementById('status_' + envKey);
  if (input.value.length > 10) { st.classList.add('set'); currentEnv[envKey] = input.value; }
  else { st.classList.remove('set'); delete currentEnv[envKey]; }
}

function updateModelSelect() {
  const sel = document.getElementById('modelSelect');
  const p = PROVIDERS.find(x => x.id === activeProvider);
  if (!p) return;
  sel.innerHTML = p.models.map(m => `<option value="${m}">${m}</option>`).join('');
  updateModelPreview(); sel.onchange = updateModelPreview;
}

function updateModelPreview() {
  document.getElementById('modelPreview').textContent = '当前: ' + activeProvider + '/' + document.getElementById('modelSelect').value;
}

function renderChannels() {
  const list = document.getElementById('channelList');
  list.innerHTML = CHANNELS.map(ch => {
    const enabled = enabledChannels.includes(ch.id);
    const hasTokens = ch.fields.some(f => currentEnv[f.key]);
    // WeChat (iLink) gets a special "扫码登录" shortcut that drives
    // the /api/wechat/* endpoints. The hand-typed Bot Token / Account
    // ID fields below remain available for users who already have
    // credentials from `hermes gateway setup` or from a prior session.
    const wechatExtra = ch.id === 'weixin' ? `
      <div class="field" style="margin-top:8px;">
        <button type="button" class="btn primary btn-launch" style="width:100%"
                onclick="event.stopPropagation(); startWeChatLogin()">
          📱 扫码登录微信
        </button>
        <div style="margin-top:6px;font-family:var(--font-mono);font-size:10px;color:var(--fg-muted);">
          扫码后自动写入 WEIXIN_TOKEN / WEIXIN_ACCOUNT_ID。手动配置见下方字段。
        </div>
      </div>` : '';
    return `<div class="channel-card ${enabled ? 'enabled' : ''}" id="ch-card-${ch.id}">
      <div class="channel-header" onclick="toggleChannelFields('${ch.id}')">
        <div class="channel-info">
          <span class="channel-icon">${ch.icon}</span>
          <div>
            <div class="channel-name">${ch.name}</div>
            <div class="channel-desc">${ch.desc}</div>
          </div>
        </div>
        <div class="channel-right">
          <span class="channel-status ${hasTokens?'on':'off'}">${hasTokens?'已配置':'未配置'}</span>
          <label class="switch" onclick="event.stopPropagation()">
            <input type="checkbox" ${enabled?'checked':''} onchange="toggleChannel('${ch.id}', this.checked)">
            <span class="slider"></span>
          </label>
        </div>
      </div>
      <div class="channel-fields ${enabled?'show':''}" id="ch-fields-${ch.id}">
        ${wechatExtra}
        ${ch.fields.map(f => `<div class="field">
          <label>${f.label}</label>
          <input id="ch-input-${f.key}" type="${f.type}" placeholder="${f.placeholder}"
                 value="${escapeHtml(currentEnv[f.key]||'')}"
                 oninput="currentEnv['${f.key}']=this.value; updateChannelStatus('${ch.id}')">
        </div>`).join('')}
      </div>
    </div>`;
  }).join('');
}

function toggleChannel(chId, checked) {
  if (checked) { if (!enabledChannels.includes(chId)) enabledChannels.push(chId); }
  else { enabledChannels = enabledChannels.filter(x => x !== chId); }
  const card = document.getElementById('ch-card-' + chId);
  card.classList.toggle('enabled', checked);
  const fields = document.getElementById('ch-fields-' + chId);
  if (checked) fields.classList.add('show');
}

function toggleChannelFields(chId) {
  const fields = document.getElementById('ch-fields-' + chId);
  fields.classList.toggle('show');
}

function updateChannelStatus(chId) {
  const ch = CHANNELS.find(x => x.id === chId);
  const card = document.getElementById('ch-card-' + chId);
  const status = card.querySelector('.channel-status');
  const hasTokens = ch.fields.some(f => currentEnv[f.key]);
  status.className = 'channel-status ' + (hasTokens ? 'on' : 'off');
  status.textContent = hasTokens ? '已配置' : '未配置';
}

function restoreConfig() {
  fetch('/api/config').then(r => r.json()).then(data => {
    const cfg = data.config || {};
    if (cfg.agent) document.getElementById('maxTurns').value = cfg.agent.max_turns || 90;
    if (cfg.terminal) document.getElementById('timeout').value = cfg.terminal.timeout || 180;
    if (cfg.compression) document.getElementById('compression').checked = cfg.compression.enabled !== false;
    if (cfg.display) {
      document.getElementById('showCost').checked = cfg.display.show_cost !== false;
      document.getElementById('showToolProgress').checked = cfg.display.tool_progress !== false;
    }
    if (cfg.memory) document.getElementById('memoryEnabled').checked = cfg.memory.memory_enabled !== false;
    if (cfg.model) {
      const full = cfg.model.default || '';
      const provider = cfg.model.provider || 'openrouter';
      selectProvider(provider);
      const sel = document.getElementById('modelSelect');
      for (let opt of sel.options) {
        if (opt.value === full || full.endsWith(opt.value)) { opt.selected = true; break; }
      }
      updateModelPreview();
    }
    if (cfg.gateway && cfg.gateway.platforms) {
      enabledChannels = Object.keys(cfg.gateway.platforms).filter(k => cfg.gateway.platforms[k].enabled);
      renderChannels();
    }
    // Surface the upstream model catalog freshness so users know
    // when the OpenRouter / Nous list was last updated. When the
    // backend couldn't reach the catalog this just stays hidden.
    const cs = document.getElementById('catalogStatus');
    if (cs) {
      if (data.catalog_updated_at) {
        cs.style.display = 'block';
        cs.textContent = '◉ 模型清单 · 上游同步于 ' + data.catalog_updated_at.slice(0,10);
        cs.style.color = 'var(--emerald,#d4e600)';
      } else {
        cs.style.display = 'block';
        cs.textContent = '◌ 模型清单 · 离线（使用内置快照）';
        cs.style.color = 'var(--fg-muted,#9a968e)';
      }
    }
  }).catch(() => {});
}

function saveConfig() {
  const sel = document.getElementById('modelSelect');
  const data = {
    env: currentEnv,
    model_provider: activeProvider,
    model_name: sel.value,
    max_turns: parseInt(document.getElementById('maxTurns').value),
    timeout: parseInt(document.getElementById('timeout').value),
    compression: document.getElementById('compression').checked,
    compression_threshold: 0.50,
    show_cost: document.getElementById('showCost').checked,
    show_tool_progress: document.getElementById('showToolProgress').checked,
    memory_enabled: document.getElementById('memoryEnabled').checked,
    enabled_channels: enabledChannels,
    skin: 'default',
  };
  const p = PROVIDERS.find(x => x.id === activeProvider);
  if (p && !currentEnv[p.env]) { toast('请填写 ' + p.name + ' API Key', 'error'); return; }

  fetch('/api/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data) })
    .then(r => r.json()).then(res => {
      if (res.success) { toast('已保存', 'success'); savedOnce = true; if(isFirstRun) updateStep(3); }
      else toast(res.error || '错误', 'error');
    }).catch(() => toast('网络错误', 'error'));
}

function launchHermes() {
  if (!savedOnce) { toast('请先保存', 'error'); return; }
  fetch('/api/launch', { method:'POST' }).then(r => r.json()).then(res => {
    if (res.success) { toast('Hermes 已启动', 'success'); setTimeout(() => window.close(), 1500); }
  });
}

function toast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.className = 'toast ' + type + ' show';
  setTimeout(() => el.classList.remove('show'), 3000);
}

function testConnection() {
  const p = PROVIDERS.find(x => x.id === activeProvider);
  if (!p) return;
  const keyInput = document.getElementById('apiKey_' + p.env);
  const key = keyInput ? keyInput.value : '';
  if (!key || key.length < 10) {
    toast('请先填写 API Key', 'error');
    return;
  }
  const result = document.getElementById('testResult');
  result.style.display = 'block';
  result.innerHTML = '<span style="color:var(--warning)">正在测试...</span>';

  fetch('/api/test', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({provider: activeProvider, api_key: key, model: ''})
  }).then(r => r.json()).then(data => {
    if (data.success) {
      result.innerHTML = '<span style="color:var(--emerald)">✓ ' + (data.message || '连接成功') + '</span>';
      // Advance onboarding step
      if (isFirstRun) {
        updateStep(2);
        document.getElementById('launchBtn').disabled = false;
      }
    } else {
      result.innerHTML = '<span style="color:var(--destructive)">✗ ' + (data.error || '连接失败') + '</span>';
    }
  }).catch(() => {
    result.innerHTML = '<span style="color:var(--destructive)">✗ 网络错误</span>';
  });
}

function checkUpdate() {
  const info = document.getElementById('versionInfo');
  const action = document.getElementById('updateAction');
  info.innerHTML = '<span style="color:var(--warning)">正在检查...</span>';
  action.style.display = 'none';
  fetch('/api/version').then(r => r.json()).then(data => {
    let html = '';
    html += '<div style="color:var(--fg);margin-bottom:4px">当前: <span style="color:var(--emerald)">' + data.local + '</span></div>';
    if (data.remote && data.remote.date) {
      html += '<div>远程: ' + data.remote.date + ' (' + data.remote.sha + ')</div>';
      html += '<div style="opacity:0.7;margin-top:2px">' + (data.remote.message || '') + '</div>';
    } else if (data.remote && data.remote.error) {
      html += '<div style="color:var(--destructive)">检查失败: ' + data.remote.error + '</div>';
    }
    if (!data.has_git) {
      html += '<div style="color:var(--warning);margin-top:6px">⚠ 非 git 克隆，需要重新构建才能更新</div>';
    }
    info.innerHTML = html;
    if (data.update_available) {
      action.style.display = 'block';
    }
    if (data.portable_update && data.portable_update.tag) {
      info.innerHTML += '<div style="margin-top:8px;color:var(--emerald)">Portable 更新: ' + data.portable_update.tag + '</div>';
    }
  }).catch(() => {
    info.innerHTML = '<span style="color:var(--destructive)">检查失败</span>';
  });
}

function runUpdate() {
  const log = document.getElementById('updateLog');
  const action = document.getElementById('updateAction');
  log.style.display = 'block';
  log.textContent = '正在更新，请稍候...\n';
  action.style.display = 'none';
  fetch('/api/update/run', { method: 'POST' }).then(r => r.json()).then(() => {
    log.textContent += '正在拉取最新代码并安装依赖...\n';
    // Poll for completion
    let checks = 0;
    const timer = setInterval(() => {
      checks++;
      fetch('/api/version').then(r => r.json()).then(data => {
        if (data.update_available === false || checks > 30) {
          clearInterval(timer);
          log.textContent = '更新完成！\n当前版本: ' + data.local + '\n';
          toast('更新完成', 'success');
        }
      }).catch(() => {
        if (checks > 30) {
          clearInterval(timer);
          log.textContent += '更新超时，请手动检查\n';
          toast('更新超时', 'error');
        }
      });
    }, 3000);
  }).catch(() => {
    log.textContent += '更新失败\n';
    toast('更新失败', 'error');
  });
}

// Auto-check version on load
setTimeout(checkUpdate, 1000);


// ====== UX Features: Export/Import/View/Reset ======
function exportConfig() {
  window.location.href = '/api/export';
  toast('配置已下载', 'success');
}

function startImport() {
  document.getElementById('importFileInput').click();
}

function doImport(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const cfg = JSON.parse(e.target.result);
      fetch('/api/import', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(cfg)
      }).then(r => r.json()).then(data => {
        if (data.success) {
          toast('配置已导入，刷新页面生效', 'success');
          setTimeout(() => location.reload(), 1000);
        } else {
          toast('导入失败: ' + (data.error || '未知错误'), 'error');
        }
      });
    } catch (err) {
      toast('JSON 格式错误', 'error');
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

function viewEnv() {
  fetch('/api/config').then(r => r.json()).then(data => {
    const env = data.env || {};
    const lines = Object.keys(env).map(k => k + '=' + (env[k].length > 20 ? env[k].slice(0,8)+'...'+env[k].slice(-4) : env[k]));
    const w = window.open('', '_blank');
    if (w) {
      w.document.write('<pre style="font-family:monospace;padding:20px;background:#170d02;color:#f5f5f5;font-size:13px;line-height:1.6;">'+lines.join('\n')+'</pre>');
      w.document.title = 'Hermes .env';
    } else {
      toast('请允许弹窗', 'error');
    }
  });
}

function resetConfig() {
  if (!confirm('确定要重置所有配置吗？\n当前配置会备份到 data/backups/')) return;
  fetch('/api/reset', { method: 'POST' }).then(r => r.json()).then(data => {
    if (data.success) {
      toast('已重置，刷新页面', 'success');
      setTimeout(() => location.reload(), 1000);
    } else {
      toast('重置失败: ' + (data.error || '未知错误'), 'error');
    }
  });
}

// ====== Status check (Hermes process + Web UI) ======
function _setLiveStatus(cls, text) {
  var line = document.getElementById('liveStatusLine');
  if (line) { line.className = cls; line.textContent = text; }
}
function checkStatus() {
  fetch('/api/status').then(r => r.json()).then(data => {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const restartBtn = document.getElementById('restartBtn');
    if (data.running) {
      dot.style.background = '#10b981';
      dot.style.boxShadow = '0 0 6px #10b981';
      text.textContent = 'Hermes 运行中 (PID ' + data.pid + ')';
      _setLiveStatus('p', '  ✓ hermes running · pid ' + data.pid);
      if (restartBtn) restartBtn.style.display = '';
    } else {
      dot.style.background = '#666';
      dot.style.boxShadow = 'none';
      _setLiveStatus('t', '  · hermes not running — click 启动');
      text.textContent = 'Hermes 未运行';
      if (restartBtn) restartBtn.style.display = 'none';
    }
  }).catch(() => {});
}

function restartHermes() {
  if (!confirm('确定要重启 Hermes？\n你需要在终端中重新启动它。')) return;
  fetch('/api/restart', { method: 'POST' }).then(r => r.json()).then(data => {
    if (data.success) {
      toast('已发送重启信号，请在终端重新启动 Hermes', 'success');
      setTimeout(checkStatus, 2000);
    } else {
      toast('重启失败', 'error');
    }
  });
}

// ====== Log viewer ======
function refreshLogs() {
  const el = document.getElementById('logContent');
  el.textContent = '加载中...';
  fetch('/api/logs').then(r => r.json()).then(data => {
    if (data.lines && data.lines.length) {
      el.textContent = data.lines.join('\n');
      el.scrollTop = el.scrollHeight;
    } else {
      el.textContent = '暂无日志';
    }
  }).catch(() => { el.textContent = '加载失败'; });
}

function clearLogView() {
  document.getElementById('logContent').textContent = '已清空（仅清空显示，不删除日志文件）';
}

// Auto-check status every 5s
checkStatus();
setInterval(checkStatus, 5000);

// ====== WeChat (iLink) QR login flow ======
let _wechatSession = null;
let _wechatPolling = false;

function _wechatModal() {
  let modal = document.getElementById('wechatModal');
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'wechatModal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(4,28,28,0.92);z-index:8000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(6px);';
  modal.innerHTML = `
    <div style="background:var(--card,#1a1208);border:1px solid var(--border,#f5f5f526);padding:28px 24px;max-width:380px;width:90%;text-align:center;font-family:var(--font-sans);">
      <h3 style="font-family:var(--font-serif);font-size:1.4rem;margin-bottom:8px;color:var(--fg,#f5f5f5);letter-spacing:0;">扫码登录微信</h3>
      <p id="wechatModalHint" style="font-family:var(--font-mono);font-size:11px;color:var(--fg-muted,#9a968e);letter-spacing:0.04em;margin-bottom:16px;">使用微信扫描下方二维码，完成手机端确认即可</p>
      <div id="wechatQrBox" style="background:white;padding:12px;min-width:240px;min-height:240px;display:flex;align-items:center;justify-content:center;">
        <span style="color:#666;font-family:monospace;font-size:12px;">加载中…</span>
      </div>
      <div id="wechatStatusLine" style="margin-top:14px;font-family:var(--font-mono);font-size:11px;color:var(--fg-muted,#9a968e);min-height:1.4em;letter-spacing:0.04em;"></div>
      <div style="display:flex;gap:8px;margin-top:18px;">
        <button type="button" class="btn" style="flex:1" onclick="cancelWeChatLogin()">关闭</button>
        <button type="button" class="btn primary btn-launch" style="flex:1" id="wechatRetryBtn" onclick="startWeChatLogin()" disabled>重试</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  return modal;
}

function _setWechatStatus(text, isError) {
  const el = document.getElementById('wechatStatusLine');
  if (!el) return;
  el.textContent = text || '';
  el.style.color = isError ? 'var(--destructive,#fb2c36)' : 'var(--fg-muted,#9a968e)';
}

function _renderWechatQr(dataUrl, rawContent) {
  const box = document.getElementById('wechatQrBox');
  if (!box) return;
  if (dataUrl) {
    box.innerHTML = `<img src="${dataUrl}" alt="WeChat QR" style="width:240px;height:240px;display:block;">`;
  } else if (rawContent) {
    // Fallback when both PNG renderers failed — let the user copy
    // the raw URL into any QR generator app.
    box.innerHTML = `<pre style="margin:0;padding:8px;color:#333;font-family:monospace;font-size:10px;word-break:break-all;white-space:pre-wrap;max-width:240px;">${escapeHtml(rawContent)}</pre>`;
  } else {
    box.innerHTML = '<span style="color:#999;font-family:monospace;font-size:12px;">二维码生成失败</span>';
  }
}

async function startWeChatLogin() {
  const modal = _wechatModal();
  modal.style.display = 'flex';
  document.getElementById('wechatRetryBtn').disabled = true;
  _setWechatStatus('正在请求二维码…');
  _renderWechatQr('', '');
  try {
    const r = await fetch('/api/wechat/start', { method: 'POST' });
    const data = await r.json();
    if (!data || !data.success) {
      _setWechatStatus('启动失败：' + (data && data.error || '未知错误'), true);
      document.getElementById('wechatRetryBtn').disabled = false;
      return;
    }
    _wechatSession = data.session;
    _renderWechatQr(data.qr_data_url, data.qr_content);
    _setWechatStatus('请使用微信扫码并在手机上确认');
    _pollWeChatStatus();
  } catch (e) {
    _setWechatStatus('网络错误：' + e.message, true);
    document.getElementById('wechatRetryBtn').disabled = false;
  }
}

async function _pollWeChatStatus() {
  if (_wechatPolling || !_wechatSession) return;
  _wechatPolling = true;
  try {
    while (_wechatSession) {
      let result;
      try {
        const r = await fetch('/api/wechat/status?session=' + encodeURIComponent(_wechatSession));
        result = await r.json();
      } catch (e) {
        _setWechatStatus('网络中断，重试中…', true);
        await new Promise(r => setTimeout(r, 2000));
        continue;
      }
      const s = (result && result.status) || 'wait';
      if (s === 'wait') {
        _setWechatStatus('等待扫码…');
        // The server-side long-poll already takes ~35s, so usually we
        // wait that long naturally. But if iLink ever returns 'wait'
        // immediately (or our long-poll times out client-side fast),
        // pace ourselves so we don't hot-loop.
        await new Promise(r => setTimeout(r, 1500));
        continue;
      }
      if (s === 'scanned') {
        _setWechatStatus('已扫码，请在手机上点击确认');
        await new Promise(r => setTimeout(r, 1500));
        continue;
      }
      if (s === 'refreshed') {
        _renderWechatQr(result.qr_data_url, result.qr_content);
        _setWechatStatus('二维码已刷新，请重新扫描');
        continue;
      }
      if (s === 'confirmed') {
        _setWechatStatus('登录成功！凭据已保存。', false);
        toast('微信登录成功 ✓ 重启 Hermes 后生效', 'success');
        // The backend already wrote credentials atomically to data/.env.
        // We MUST refetch the server-side env instead of injecting
        // placeholder values into currentEnv — sending a placeholder
        // back to /api/save would clobber the real token (saveConfig
        // writes data.env verbatim into .env). Refetch keeps the
        // in-browser mirror in sync with what's on disk.
        try {
          const r2 = await fetch('/api/config');
          const fresh = await r2.json();
          if (fresh && fresh.env) {
            // Replace the env reference so subsequent save_config()
            // calls send the canonical disk-backed values.
            for (const k of Object.keys(fresh.env)) {
              currentEnv[k] = fresh.env[k];
            }
          }
        } catch (_) { /* best effort — backend wrote, that's what matters */ }
        // Reflect new account_id in the visible input
        const accountId = (result && result.account_id) || currentEnv['WEIXIN_ACCOUNT_ID'] || '';
        const aiInput = document.getElementById('ch-input-WEIXIN_ACCOUNT_ID');
        if (aiInput && accountId) aiInput.value = accountId;
        // Auto-enable the channel since the user just authenticated.
        if (!enabledChannels.includes('weixin')) enabledChannels.push('weixin');
        renderChannels();
        setTimeout(() => cancelWeChatLogin(false), 1500);
        break;
      }
      if (s === 'expired') {
        _setWechatStatus('二维码已过期：' + (result.message || ''), true);
        document.getElementById('wechatRetryBtn').disabled = false;
        _wechatSession = null;
        break;
      }
      if (s === 'error') {
        _setWechatStatus('错误：' + (result.message || '未知'), true);
        document.getElementById('wechatRetryBtn').disabled = false;
        _wechatSession = null;
        break;
      }
      // Unknown status — keep polling
    }
  } finally {
    _wechatPolling = false;
  }
}

function cancelWeChatLogin(closeModal) {
  if (closeModal === undefined) closeModal = true;
  const session = _wechatSession;
  _wechatSession = null;
  if (session) {
    fetch('/api/wechat/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session })
    }).catch(() => {});
  }
  if (closeModal) {
    const modal = document.getElementById('wechatModal');
    if (modal) modal.style.display = 'none';
  }
}

// ====== Disconnect detection ======
(function() {
  let failures = 0;
  setInterval(() => {
    fetch('/api/heartbeat').then(r => {
      if (r.ok) { failures = 0; return; }
      failures++;
    }).catch(() => { failures++; });
    if (failures >= 3) {
      let overlay = document.getElementById('disconnectOverlay');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'disconnectOverlay';
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(4,28,28,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px);';
        overlay.innerHTML = '<div style="background:#1a1208;padding:32px 40px;border-radius:14px;text-align:center;border:1px solid rgba(237,255,69,0.15);max-width:360px;"><h3 style="color:#f5f5f5;margin-bottom:8px;font-size:1em;">连接已断开</h3><p style="color:#9a968e;font-size:0.85em;line-height:1.6;">Hermes 进程已停止。请重新双击启动器。</p></div>';
        document.body.appendChild(overlay);
      }
    }
  }, 5000);
})();

init();

  // Hermes Web UI integration
  async function toggleWebUI() {
    const btn = document.getElementById('webui-btn');
    try {
      const res = await fetch('/api/webui/status');
      const data = await res.json();
      if (data.running) {
        window.open('http://127.0.0.1:8648', '_blank');
      } else {
        btn.textContent = '启动中...';
        btn.disabled = true;
        const startRes = await fetch('/api/webui/start');
        const startData = await startRes.json();
        if (startData.ok) {
          setTimeout(() => {
            window.open('http://127.0.0.1:8648', '_blank');
            btn.textContent = '打开';
            btn.disabled = false;
          }, 2000);
        } else {
          btn.textContent = '启动失败';
          btn.disabled = false;
        }
      }
    } catch (err) {
      btn.textContent = '错误';
      btn.disabled = false;
    }
  }
</script>

</main>

<footer class="y-footer">
  <div class="c"><span class="y-label y-op-7">yu.ai</span></div>
  <div class="c"><span class="y-label y-op-5">hermes portable</span></div>
  <div class="c"><span class="y-label y-op-5" style="color:var(--accent)">hermes config</span></div>
</footer>

<script>
(function(){
  function lsGet(k){try{return localStorage.getItem(k);}catch(_){return null;}}
  function lsSet(k,v){try{localStorage.setItem(k,v);}catch(_){}}
  var btn=document.getElementById("y-theme-btn");
  if(!btn) return;
  var html=document.documentElement;
  var sun=btn.querySelector(".y-theme-sun");
  var moon=btn.querySelector(".y-theme-moon");
  function syncIcons(isLight){sun.style.display=isLight?"none":"block";moon.style.display=isLight?"block":"none";}
  var saved=lsGet("yuai-theme");
  if(saved==="light"){html.setAttribute("data-theme","light");syncIcons(true);}
  else if(saved==="dark"){html.setAttribute("data-theme","dark");syncIcons(false);}
  else{var mql=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)");syncIcons(mql&&mql.matches);}
  btn.onclick=function(){
    var nowLight=html.getAttribute("data-theme")!=="light";
    if(!html.getAttribute("data-theme")){var sysLight=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches;nowLight=!sysLight;}
    html.setAttribute("data-theme",nowLight?"light":"dark");
    lsSet("yuai-theme",nowLight?"light":"dark");
    syncIcons(nowLight);
  };
})();

  // Hermes Web UI integration
  
</script>
</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
#  HTTP SERVER
# ═══════════════════════════════════════════════════════════════

def _extract_date(s):
    """Extract a date string like 2026-04-15 from a version string."""
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", str(s))
    return m.group(1) if m else ""


def _detect_release_asset_label():
    """Compute the platform label that matches our release assets.

    Release assets are named:
      HermesPortable-macOS-arm64.zip
      HermesPortable-macOS-x64.zip
      HermesPortable-Linux-x64.zip
      HermesPortable-Linux-arm64.zip
      HermesPortable-Windows-x64.zip
      HermesPortable-Universal.zip
    Returns e.g. "macOS-arm64" / "Linux-x64" / "Windows-x64" or None if
    we can't tell.
    """
    import platform as _p
    system = _p.system()
    arch = _p.machine().lower()
    if arch in ("x86_64", "amd64"):
        arch = "x64"
    elif arch in ("aarch64", "arm64"):
        arch = "arm64"
    sys_label = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(system)
    if not sys_label:
        return None
    return f"{sys_label}-{arch}"


def _pick_release_asset(release):
    """Pick the right asset for THIS host out of a GitHub release.

    Bug fix: the previous code blindly took ``assets[0]`` which is
    alphabetically the first one — in practice always
    ``HermesPortable-Linux-arm64.zip``. Mac and Windows users who
    clicked "Check for Updates" got a Linux-ARM zip dumped on top of
    their installation, corrupting the venv.

    Strategy:
      1. Look for an asset matching the host's platform label exactly
         (HermesPortable-macOS-arm64.zip on Apple Silicon, etc).
      2. Fall back to the Universal zip if available (it carries
         per-platform venvs and works everywhere).
      3. Return None if neither matches — caller surfaces an error
         rather than installing the wrong thing.
    """
    assets = (release or {}).get("assets") or []
    if not assets:
        return None
    label = _detect_release_asset_label()
    universal = None
    exact = None
    for a in assets:
        name = (a or {}).get("name", "")
        if not isinstance(name, str):
            continue
        if not name.endswith(".zip"):
            continue
        if "Universal" in name:
            universal = a
            continue
        if label and label in name:
            exact = a
            # don't break; in case of duplicates we want the first
            # exact match, which is what we already have
            break
    return exact or universal


class ConfigHandler(SimpleHTTPRequestHandler):
    # 防止单个请求挂死整个线程：30 秒超时
    timeout = 30
    rbufsize = 1
    wbufsize = 0

    def _host_ok(self):
        """Reject Host headers other than 127.0.0.1:<port> / localhost:<port>.

        DNS-rebinding defense. This panel reads and writes data/.env —
        i.e. EVERY provider API key and channel token. If a malicious
        page makes the user's browser resolve attacker.com to 127.0.0.1,
        the browser will happily send requests here with Host:
        attacker.com; the same-origin policy treats that as a different
        origin from ours, so attacker JS could read /api/config (all the
        keys) or POST /api/save. Pinning Host to localhost blocks it.

        chat_viewer.py has had this since v0.14.2 — config_server.py is
        the MORE sensitive surface and was missing it. (parity fix)
        """
        host = self.headers.get("Host", "")
        try:
            port = self.server.server_address[1]
        except Exception:
            port = PORT
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _reject_bad_host(self):
        """Send 421 and return True if the Host header is not localhost."""
        if self._host_ok():
            return False
        self.send_response(421)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(b'{"error":"Misdirected request: Host mismatch"}')
        return True

    def do_GET(self):
        try:
            if self._reject_bad_host():
                return
            self._dispatch_get()
        except Exception as e:
            print(f"GET {self.path} error: {e}", file=sys.stderr)
            try:
                self._json_response({"error": str(e)[:200]})
            except Exception:
                pass

    def _dispatch_get(self):
        # Normalize the request line: strip query string and fragment
        # for path-based routing. urllib's split makes us forgiving of
        # things like /icons/openai.svg?v=2, /api/config?_=cachebust,
        # which the previous exact-match `self.path == "/api/foo"`
        # checks would 404 on. Routes that NEED the query (currently
        # only /api/wechat/status) keep reading self.path directly.
        from urllib.parse import urlsplit
        path_only = urlsplit(self.path).path
        if path_only in ("/", "/index.html"):
            self._serve_html()
        elif path_only == "/favicon.svg":
            self._serve_favicon()
        elif path_only.startswith("/icons/") and path_only.endswith(".svg"):
            self._serve_icon(path_only[7:])  # strip "/icons/"
        elif path_only == "/api/bootstrap":
            # Token endpoint (localhost only)
            origin = self.headers.get("Origin", "")
            if origin and not _is_local_origin(origin):
                self.send_error(403, "Forbidden")
                return
            self._json_response({
                "token": SERVER_TOKEN,
                "port": actual_port
            })
        elif path_only == "/api/config":
            self._json_response(read_config())
        elif path_only == "/api/version":
            self._json_response(self._get_version())
        elif path_only == "/api/heartbeat":
            self._json_response({"alive": True})
        elif path_only == "/api/export":
            self._serve_export()
        elif path_only == "/api/status":
            self._json_response(self._get_status())
        elif path_only == "/api/logs":
            self._json_response(self._get_logs())
        elif path_only == "/api/wechat/status":
            # GET /api/wechat/status?session=xxx — long-poll, may take 35s.
            # Reads self.path directly to keep query string.
            self._serve_wechat_status()
        elif path_only == '/api/webui/status':
            self._json_response({'running': webui_status()})
        elif path_only == '/api/webui/start':
            if webui_start():
                self._json_response({'ok': True, 'port': WEB_UI_PORT})
            else:
                self._json_response({'ok': False, 'error': 'Failed to start'}, 500)
        elif path_only == '/api/webui/stop':
            if webui_stop():
                self._json_response({'ok': True})
            else:
                self._json_response({'ok': False, 'error': 'Failed to stop'}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            if self._reject_bad_host():
                return
            self._dispatch_post()
        except Exception as e:
            print(f"POST {self.path} error: {e}", file=sys.stderr)
            try:
                self._json_response({"success": False, "error": str(e)[:200]})
            except Exception:
                pass

    def _dispatch_post(self):
        body = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 1_000_000))
        if self.path == "/api/save":
            try:
                data = json.loads(body)
                save_config(data)
                self._json_response({"success": True})
            except Exception as e:
                self._json_response({"success": False, "error": str(e)})
        elif self.path == "/api/launch":
            self._json_response({"success": True})
            threading.Thread(target=self._launch_hermes, daemon=True).start()
        elif self.path == "/api/update/run":
            self._json_response({"success": True, "message": "Updating..."})
            threading.Thread(target=self._run_update, daemon=True).start()
        elif self.path == "/api/test":
            try:
                data = json.loads(body)
                result = self._test_provider(data)
                self._json_response(result)
            except Exception as e:
                self._json_response({"success": False, "error": str(e)})
        elif self.path == "/api/import":
            try:
                data = json.loads(body)
                self._do_import(data)
                self._json_response({"success": True})
            except Exception as e:
                self._json_response({"success": False, "error": str(e)})
        elif self.path == "/api/reset":
            try:
                self._do_reset()
                self._json_response({"success": True})
            except Exception as e:
                self._json_response({"success": False, "error": str(e)})
        elif self.path == "/api/restart":
            self._json_response({"success": True})
            threading.Thread(target=self._restart_hermes, daemon=True).start()
        elif self.path == "/api/wechat/start":
            try:
                payload = wechat_start_login()
                self._json_response({"success": True, **payload})
            except Exception as e:
                self._json_response({"success": False, "error": str(e)[:300]})
        elif self.path == "/api/wechat/cancel":
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            wechat_cancel_login((data or {}).get("session"))
            self._json_response({"success": True})
        else:
            self.send_error(404)

    def _serve_html(self):
        config = read_config()
        page = HTML_PAGE
        page = page.replace("__PROVIDERS__", json.dumps(config["providers"]))
        page = page.replace("__CHANNELS__", json.dumps(config["channels"]))
        page = page.replace("__ACTIVE_PROVIDER__", config["active_provider"])
        page = page.replace("__CURRENT_ENV__", json.dumps(config["env"]))
        gw = config["config"].get("gateway", {})
        platforms = gw.get("platforms", {})
        enabled = [k for k, v in platforms.items() if v.get("enabled")]
        page = page.replace("__ENABLED_CHANNELS__", json.dumps(enabled))
        # Detect first run: no API key configured
        has_key = any(config["env"].get(p["env"]) for p in config["providers"])
        page = page.replace("__FIRST_RUN__", "true" if not has_key else "false")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' 'unsafe-eval'")
        self.end_headers()
        self.wfile.write(page.encode())

    def _serve_favicon(self):
        favicon_path = PORTABLE_ROOT / "favicon.svg"
        if favicon_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.end_headers()
            self.wfile.write(favicon_path.read_bytes())
        else:
            self.send_error(404)

    def _serve_icon(self, filename):
        """Serve SVG icons from the icons/ directory."""
        import re
        # Security: only allow simple filenames (alphanumeric + hyphen + .svg)
        if not re.match(r'^[a-zA-Z0-9_-]+\.svg$', filename):
            self.send_error(400)
            return
        icon_path = PORTABLE_ROOT / "icons" / filename
        if icon_path.exists() and icon_path.resolve().parent == (PORTABLE_ROOT / "icons").resolve():
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(icon_path.read_bytes())
        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _get_version(self):
        import urllib.request
        # Local version
        if sys.platform == "win32":
            hermes_bin = VENV_DIR / "Scripts" / "hermes.exe"
        else:
            hermes_bin = VENV_DIR / "bin" / "hermes"
        local = "unknown"
        if hermes_bin.exists():
            try:
                r = subprocess.run(
                    [str(hermes_bin), "--version"],
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, "HERMES_HOME": str(DATA_DIR)},
                )
                for line in r.stdout.splitlines():
                    if "Hermes Agent" in line:
                        local = line.strip()
                        break
            except Exception:
                pass
        # Remote version
        remote = {}
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/NousResearch/hermes-agent/commits?per_page=1",
                headers={"User-Agent": "HermesPortable/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data:
                    remote = {
                        "sha": data[0]["sha"][:8],
                        "date": data[0]["commit"]["committer"]["date"][:10],
                        "message": data[0]["commit"]["message"].split("\n")[0][:60],
                    }
        except Exception as e:
            remote = {"error": str(e)}
        # Check if git-based
        has_git = (PORTABLE_ROOT / "hermes-agent" / ".git").exists()

        # Also check portable releases from GitHub
        portable_update = {}
        try:
            req2 = urllib.request.Request(
                f"https://api.github.com/repos/{PORTABLE_REPO}/releases/latest",
                headers={"User-Agent": "HermesPortable/1.0"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                release = json.loads(resp2.read())
                portable_update = {
                    "tag": release.get("tag_name", ""),
                    "body": release.get("body", "")[:300],
                    "url": release.get("html_url", ""),
                    "download": (
                        # Prefer the asset matching this host. Falling
                        # back to assets[0] would always point at the
                        # alphabetically first asset (Linux-arm64) for
                        # Mac/Windows users — see _pick_release_asset.
                        (_pick_release_asset(release) or {}).get("browser_download_url")
                        if release.get("assets") else None
                    ),
                }
        except Exception:
            pass

        # Determine if portable update is available
        current_tag = ""
        version_file = PORTABLE_ROOT / "VERSION"
        if version_file.exists():
            current_tag = version_file.read_text().strip()
        portable_is_newer = (
            portable_update.get("tag", "") != ""
            and portable_update["tag"].lstrip("v") != current_tag
        )

        return {
            "local": local,
            "local_tag": current_tag,
            "remote": remote,
            "has_git": has_git,
            "update_available": (
                "date" in remote
                and "20" in str(local)
                and remote.get("date", "") > _extract_date(local)
            ) if has_git else portable_is_newer,
            "portable_update": portable_update if portable_is_newer else None,
        }

    def _run_update(self):
        import urllib.request
        import zipfile
        import tempfile
        import socket
        # 局部超时管理：保存原值，函数结束后恢复
        # 防止影响其他线程的 urllib 调用（如 _get_version 已有自己的 timeout）
        _orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(60)
        try:

            update_script = PORTABLE_ROOT / "lib" / "update.py"
            has_git = (PORTABLE_ROOT / "hermes-agent" / ".git").exists()

            # Check if SCRIPT_DIR is writable (some USB mounts are read-only)
            try:
                test_file = PORTABLE_ROOT / ".write_test"
                test_file.touch()
                test_file.unlink()
            except (OSError, PermissionError) as e:
                print(f"Update failed: PORTABLE_ROOT is not writable ({e})", file=sys.stderr)
                return

            # If git-based, use the existing update.py
            if has_git and update_script.exists():
                pass  # fall through to existing logic below
            else:
                # Release-based update: download zip from GitHub Releases
                try:
                    req = urllib.request.Request(
                        f"https://api.github.com/repos/{PORTABLE_REPO}/releases/latest",
                        headers={"User-Agent": "HermesPortable/1.0"},
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        release = json.loads(resp.read())
                    assets = release.get("assets", [])
                    if not assets:
                        print("Update failed: release has no assets",
                              file=sys.stderr)
                        return

                    asset = _pick_release_asset(release)
                    if asset is None:
                        # No exact platform match and no Universal
                        # fallback. Refuse rather than blindly grabbing
                        # assets[0] (the v0.14.x bug — see
                        # _pick_release_asset docstring).
                        host_label = _detect_release_asset_label() or "unknown"
                        print(
                            f"Update failed: no release asset matches host "
                            f"({host_label}); available: "
                            f"{[a.get('name') for a in assets]}",
                            file=sys.stderr,
                        )
                        return
                    download_url = asset["browser_download_url"]
                    tmp_zip = Path(tempfile.gettempdir()) / "hermes-portable-update.zip"
                    tmp_extract = Path(tempfile.gettempdir()) / "hermes-portable-extract"

                    # Download
                    urllib.request.urlretrieve(download_url, str(tmp_zip))

                    # Extract — with zip-slip protection.
                    # zipfile.extractall doesn't reject members with
                    # absolute paths or `..` segments on Python < 3.12,
                    # which lets a malicious / corrupt release write
                    # arbitrary files outside tmp_extract. Validate every
                    # member's resolved path before extracting.
                    if tmp_extract.exists():
                        import shutil
                        shutil.rmtree(tmp_extract)
                    tmp_extract.mkdir(parents=True, exist_ok=True)
                    extract_root = tmp_extract.resolve()
                    with zipfile.ZipFile(str(tmp_zip), 'r') as zf:
                        for member in zf.infolist():
                            name = member.filename
                            if not name or name.endswith("/"):
                                # Directory or empty entry — Python
                                # creates parents on demand for files,
                                # so we don't have to materialize these,
                                # but we still need to validate them.
                                pass
                            # Reject absolute paths and Windows drive
                            # letters outright.
                            if name.startswith(("/", "\\")) or (
                                len(name) > 1 and name[1] == ":"
                            ):
                                raise RuntimeError(
                                    f"Refusing zip member with absolute "
                                    f"path: {name!r}")
                            target = (tmp_extract / name).resolve()
                            try:
                                target.relative_to(extract_root)
                            except ValueError:
                                raise RuntimeError(
                                    f"Refusing zip member that escapes "
                                    f"extract root: {name!r}")
                        zf.extractall(str(tmp_extract))

                    # Find root dir inside zip
                    entries = list(tmp_extract.iterdir())
                    src_dir = entries[0] if len(entries) == 1 and entries[0].is_dir() else tmp_extract

                    # Copy files (skip data/, venv*, python*, _home/)
                    skip_prefixes = ("data", "venv", "python", "_home", ".git")
                    import shutil
                    for item in src_dir.iterdir():
                        if any(item.name.startswith(s) for s in skip_prefixes):
                            continue
                        dest = PORTABLE_ROOT / item.name
                        if item.is_dir():
                            if dest.exists():
                                # 保留用户在该目录下添加的文件
                                for child in dest.iterdir():
                                    if (item / child.name).exists():
                                        if child.is_dir():
                                            shutil.rmtree(child)
                                        else:
                                            child.unlink()
                                # 复制新文件，不删整个目录
                                for src_child in item.iterdir():
                                    dest_child = dest / src_child.name
                                    if src_child.is_dir():
                                        if dest_child.exists():
                                            shutil.rmtree(dest_child)
                                        shutil.copytree(src_child, dest_child)
                                    else:
                                        shutil.copy2(src_child, dest_child)
                            else:
                                shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)

                    # Cleanup
                    tmp_zip.unlink(missing_ok=True)
                    shutil.rmtree(tmp_extract, ignore_errors=True)

                    # Update VERSION file
                    new_tag = release.get("tag_name", "").lstrip("v")
                    if new_tag:
                        (PORTABLE_ROOT / "VERSION").write_text(new_tag)
                    return
                except Exception as e:
                    # Surface release-zip update failures to the
                    # operator. Frontend polls /api/version for the new
                    # version; if that never changes the user is stuck
                    # without a hint why. Stderr → systemd / launchd
                    # journal / terminal where the launcher started us.
                    print(f"Update via release zip failed: {e}",
                          file=sys.stderr)
                return

            if not update_script.exists():
                return
            # Use the portable venv's python if we can find it, so update.py
            # reinstalls into the same venv hermes runs from. Fall back to
            # whatever `sys.executable` points at (usually the same anyway).
            if sys.platform == "win32":
                py = VENV_DIR / "Scripts" / "python.exe"
            else:
                py = VENV_DIR / "bin" / "python"
            if not py.exists():
                py = Path(sys.executable)
            # No timeout: a fresh `pip install` of hermes-agent + its extras
            # can easily take 5+ minutes on a cold cache; the old 120s
            # ceiling silently aborted mid-install and left the venv in a
            # half-broken state. The frontend polls /api/version for
            # completion instead of relying on us returning.
            try:
                subprocess.run([str(py), str(update_script), "update"],
                               cwd=str(PORTABLE_ROOT))
            except Exception:
                pass

        finally:
            socket.setdefaulttimeout(_orig_timeout)

    def _get_status(self):
        """Detect if hermes process is running via process listing + Web UI.

        Lock file 存的是 launcher PID（包含 hermes 子进程），不准确。
        改为遍历系统进程查找真正的 hermes 命令。
        """
        import urllib.request
        running = False
        pid = None

        # 优先查 lock file 作为 hint
        lock_file = DATA_DIR / ".hermes.lock"
        candidate_pids = []
        if lock_file.exists():
            try:
                candidate_pids.append(int(lock_file.read_text().strip()))
            except (OSError, ValueError):
                pass

        # 遍历进程查找真正的 hermes（命令行包含 venv/bin/hermes）
        venv_hermes = str(VENV_DIR / ("Scripts/hermes.exe" if sys.platform == "win32" else "bin/hermes"))
        try:
            if sys.platform == "win32":
                # wmic was removed in Windows 11 24H2+; use tasklist (CSV).
                # We can't filter by command line via tasklist, but matching
                # the image name hermes.exe is good enough — the portable
                # venv hermes.exe is the only one that should be running.
                r = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq hermes.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                import csv as _csv
                for row in _csv.reader(r.stdout.splitlines()):
                    # CSV columns: "Image Name","PID","Session Name",...
                    if len(row) >= 2 and row[0].lower() == "hermes.exe":
                        try:
                            pid = int(row[1])
                            running = True
                            break
                        except ValueError:
                            pass
            else:
                # Use ps to find process matching venv hermes path
                r = subprocess.run(
                    ["ps", "-eo", "pid,command"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in r.stdout.splitlines()[1:]:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and venv_hermes in parts[1]:
                        try:
                            pid = int(parts[0])
                            running = True
                            break
                        except ValueError:
                            pass
        except Exception:
            # Fallback to lock file if ps/wmic fails
            for p in candidate_pids:
                try:
                    if sys.platform == "win32":
                        r = subprocess.run(
                            ["tasklist", "/FI", f"PID eq {p}", "/NH"],
                            capture_output=True, text=True, timeout=5,
                        )
                        if str(p) in r.stdout:
                            running = True
                            pid = p
                            break
                    else:
                        os.kill(p, 0)
                        running = True
                        pid = p
                        break
                except (OSError, ProcessLookupError):
                    pass

        return {
            "running": running,
            "pid": pid,
        }

    def _get_logs(self):
        """Tail recent hermes logs，仅读取文件末尾 256KB 防止 OOM。"""
        candidates = [
            DATA_DIR / "logs" / "hermes.log",
            DATA_DIR / ".hermes" / "logs" / "hermes.log",
            DATA_DIR / "hermes.log",
        ]
        MAX_TAIL_BYTES = 256 * 1024  # 256KB
        for p in candidates:
            if p.exists() and p.is_file():
                try:
                    size = p.stat().st_size
                    with p.open("rb") as f:
                        if size > MAX_TAIL_BYTES:
                            f.seek(-MAX_TAIL_BYTES, 2)
                            # 跳过被截断的第一行
                            f.readline()
                        data = f.read()
                    text = data.decode("utf-8", errors="replace")
                    lines = text.splitlines()[-200:]
                    return {"source": str(p), "lines": lines, "size": size}
                except Exception as e:
                    return {"source": str(p), "lines": [f"Error reading log: {e}"]}
        return {"source": None, "lines": ["未找到日志文件。Hermes 启动后会自动生成日志。"]}

    def _restart_hermes(self):
        """Kill the running hermes process if any. 验证 kill 成功才删 lock。"""
        time.sleep(0.5)
        lock_file = DATA_DIR / ".hermes.lock"
        if not lock_file.exists():
            return
        kill_succeeded = False
        try:
            pid = int(lock_file.read_text().strip())
            if sys.platform == "win32":
                r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                kill_succeeded = (r.returncode == 0)
            else:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(5)
                try:
                    os.kill(pid, 0)
                    # 进程还活着，发 SIGKILL
                    os.kill(pid, 9)
                    time.sleep(0.5)
                    try:
                        os.kill(pid, 0)
                        # 仍然活着，kill 失败
                        kill_succeeded = False
                    except OSError:
                        kill_succeeded = True
                except OSError:
                    # 已经退出
                    kill_succeeded = True

            # 仅在确认 kill 成功后才删 lock
            if kill_succeeded:
                lock_file.unlink(missing_ok=True)
            else:
                print(f"Restart: failed to kill PID {pid}, lock retained", file=sys.stderr)
        except Exception as e:
            print(f"Restart failed: {e}", file=sys.stderr)

    def _serve_export(self):
        """Export current config as downloadable JSON."""
        cfg = read_config()
        # Strip out static provider/channel definitions, only export user-set values
        exported = {
            "env": cfg.get("env", {}),
            "config": cfg.get("config", {}),
            "active_provider": cfg.get("active_provider", ""),
        }
        body = json.dumps(exported, ensure_ascii=False, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", 'attachment; filename="hermes-config.json"')
        self.end_headers()
        self.wfile.write(body)

    def _serve_wechat_status(self):
        """GET /api/wechat/status?session=<token>

        Long-poll wrapper around wechat_check_status. The iLink server
        holds the request for ~35s; we forward the result to the
        frontend as a single JSON response per call. The frontend keeps
        polling until status==confirmed | expired | error.
        """
        import urllib.parse as _uparse
        try:
            qs = _uparse.urlsplit(self.path).query
            params = _uparse.parse_qs(qs)
            session = (params.get("session") or [""])[0]
            if not session:
                self._json_response({"status": "error",
                                     "message": "missing session"})
                return
            result = wechat_check_status(session)
            self._json_response(result)
        except Exception as e:
            self._json_response({"status": "error", "message": str(e)[:200]})

    def _do_import(self, data):
        """Import config from uploaded JSON. 事务性写入：全部成功或全部回滚。"""
        from datetime import datetime
        import shutil
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cfg_path = DATA_DIR / "config.yaml"

        # Phase 1: 备份现有文件
        env_backup = None
        cfg_backup = None
        try:
            if ENV_FILE.exists():
                env_backup = backup_dir / f".env.before-import.{ts}"
                shutil.copy(ENV_FILE, env_backup)
            if cfg_path.exists():
                cfg_backup = backup_dir / f"config.yaml.before-import.{ts}"
                shutil.copy(cfg_path, cfg_backup)
        except Exception as e:
            raise RuntimeError(f"Backup failed before import: {e}")

        # Phase 2: 写入新文件，失败时从备份恢复
        try:
            self._write_imported(data)
        except Exception as e:
            # 回滚
            try:
                if env_backup and env_backup.exists():
                    shutil.copy(env_backup, ENV_FILE)
                if cfg_backup and cfg_backup.exists():
                    shutil.copy(cfg_backup, cfg_path)
            except Exception:
                pass
            raise RuntimeError(f"Import failed, rolled back: {e}")

    def _write_imported(self, data):
        """实际写入逻辑，可能抛出异常。

        Hardening notes:
          * Every value goes through _sanitize_env_value to strip CR/LF.
            Without this, an imported value like "sk-...\\nMALICIOUS=1"
            would inject an extra env line.
          * Final write uses _atomic_write_text (tmp + os.replace) so a
            crash mid-write can't leave a half-written .env / config.yaml
            on disk. _do_import has its own backup+rollback layer above
            this; the atomic write makes that layer's job easier.
        """
        env = data.get("env", {})
        if env:
            # Build .env content. Filter via PROVIDERS / CHANNELS schema
            # so import can't smuggle in arbitrary env keys.
            lines = ["#  Hermes Portable - Imported"]
            for p in PROVIDERS:
                if p["env"] in env and env[p["env"]]:
                    lines.append(f'{p["env"]}={_sanitize_env_value(env[p["env"]])}')
                if "base_url_env" in p and p["base_url_env"] in env:
                    lines.append(f'{p["base_url_env"]}={_sanitize_env_value(env[p["base_url_env"]])}')
            # Channel keys
            for ch in CHANNELS:
                for f in ch.get("fields", []):
                    if f["key"] in env and env[f["key"]]:
                        lines.append(f'{f["key"]}={_sanitize_env_value(env[f["key"]])}')
            ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(ENV_FILE, "\n".join(lines) + "\n", encoding="utf-8")
        # Save config
        cfg_data = data.get("config", {})
        if cfg_data:
            cfg_path = DATA_DIR / "config.yaml"
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            # Use PyYAML if available, otherwise fall back to JSON (still
            # parseable by hermes' yaml loader).
            try:
                import yaml
                cfg_text = yaml.safe_dump(cfg_data, allow_unicode=True)
            except ImportError:
                cfg_text = json.dumps(cfg_data, ensure_ascii=False, indent=2)
            _atomic_write_text(cfg_path, cfg_text, encoding="utf-8")

    def _do_reset(self):
        """Backup and clear current config.

        Uses unlink(missing_ok=True) so a concurrent _do_reset or other
        deleter can't make us crash with FileNotFoundError between the
        exists() check and the unlink. Also wraps the destructive part
        in the save-config lock so a save running in parallel can't
        race against the reset.
        """
        import shutil
        from datetime import datetime
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cfg_path = DATA_DIR / "config.yaml"
        with _save_config_lock:
            if ENV_FILE.exists():
                try:
                    shutil.copy(ENV_FILE, backup_dir / f".env.{ts}")
                except FileNotFoundError:
                    pass
                ENV_FILE.unlink(missing_ok=True)
            if cfg_path.exists():
                try:
                    shutil.copy(cfg_path, backup_dir / f"config.yaml.{ts}")
                except FileNotFoundError:
                    pass
                cfg_path.unlink(missing_ok=True)

    def _test_provider(self, data):
        """Test an API key by making a minimal request."""
        import urllib.request
        provider_id = data.get("provider", "")
        api_key = data.get("api_key", "")
        model = data.get("model", "")

        if not api_key:
            return {"success": False, "error": "No API key provided"}

        # Provider-specific test endpoints
        PROVIDER_CONFIGS = {
            "openrouter": {
                "url": "https://openrouter.ai/api/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "anthropic": {
                "url": "https://api.anthropic.com/v1/messages",
                "headers": {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                "method": "POST",
                "body": json.dumps({"model": model or "claude-haiku-4-5", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}).encode(),
            },
            "openai": {
                "url": "https://api.openai.com/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "deepseek": {
                "url": "https://api.deepseek.com/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "google": {
                "url": "https://generativelanguage.googleapis.com/v1beta/models",
                "headers": {"x-goog-api-key": api_key},
            },
            "xiaomi": {
                # Xiaomi MiMo uses api.xiaomimimo.com (NOT api.xiaoai.mi.com —
                # that's Xiaomi's smart-home assistant, unrelated).
                "url": "https://api.xiaomimimo.com/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "nous": {
                "url": "https://inference-api.nousresearch.com/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "kimi": {
                "url": "https://api.moonshot.cn/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            "dashscope": {
                "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # xAI uses OpenAI-compatible /models endpoint
            "xai": {
                "url": "https://api.x.ai/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # Mistral OpenAI-compatible
            "mistral": {
                "url": "https://api.mistral.ai/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # Zhipu (Z.ai) OpenAI-compatible at open.bigmodel.cn
            "zhipu": {
                "url": "https://open.bigmodel.cn/api/paas/v4/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # MiniMax — text models are listed via the chat platform
            "minimax": {
                "url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "method": "POST",
                "body": json.dumps({"model": model or "MiniMax-M2.5", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).encode(),
            },
            # Doubao / Volcengine Ark — uses chat endpoint (no public /models list)
            "doubao": {
                "url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "method": "POST",
                "body": json.dumps({"model": model or "doubao-seed-1.6", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).encode(),
            },
            # Cerebras — OpenAI-compatible
            "cerebras": {
                "url": "https://api.cerebras.ai/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # Groq — OpenAI-compatible
            "groq": {
                "url": "https://api.groq.com/openai/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
            # Perplexity — uses chat completions, no public /models list
            "perplexity": {
                "url": "https://api.perplexity.ai/chat/completions",
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "method": "POST",
                "body": json.dumps({"model": model or "sonar", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}).encode(),
            },
            # Custom / proxy gateway — caller supplies base_url; if not provided, fail clearly
            "custom": {
                "url": (data.get("base_url") or "").rstrip("/") + "/models" if data.get("base_url") else "",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
        }

        cfg = PROVIDER_CONFIGS.get(provider_id)
        if not cfg:
            return {"success": False, "error": f"Unknown provider: {provider_id}"}
        if not cfg.get("url"):
            return {"success": False, "error": "Missing base URL for custom provider"}

        # Scheme guard — refuse to fetch local-file / javascript / data
        # / ftp URLs through the Test button. urllib.request.urlopen()
        # honors file:// natively, which would let a user-controlled
        # base_url field exfiltrate /etc/hosts or any other readable
        # file via the JSON response. Pin the scheme to http(s) for
        # every provider, including 'custom'.
        try:
            from urllib.parse import urlsplit
            scheme = urlsplit(cfg["url"]).scheme.lower()
        except Exception:
            scheme = ""
        if scheme not in ("http", "https"):
            return {
                "success": False,
                "error": f"Refusing non-http(s) URL scheme: {scheme!r}",
            }

        try:
            method = cfg.get("method", "GET")
            req = urllib.request.Request(
                cfg["url"],
                headers={**cfg["headers"], "User-Agent": "HermesPortable/1.0"},
                method=method,
            )
            if "body" in cfg:
                req.data = cfg["body"]

            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body = resp.read(2000).decode("utf-8", errors="replace")

            if status >= 200 and status < 300:
                # Try to count available models
                model_count = ""
                try:
                    models_data = json.loads(body)
                    if isinstance(models_data, dict) and "data" in models_data:
                        model_count = f" ({len(models_data['data'])} models)"
                except Exception:
                    pass
                return {
                    "success": True,
                    "message": f"Connection OK{model_count}",
                    "status": status,
                }
            else:
                return {"success": False, "error": f"HTTP {status}"}

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read(500).decode("utf-8", errors="replace")
                err_json = json.loads(error_body)
                error_body = err_json.get("error", {}).get("message", error_body[:200])
            except Exception:
                error_body = error_body[:200] if error_body else str(e)
            return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _launch_hermes(self):
        time.sleep(1)
        # Windows uses Scripts/hermes.exe, Unix uses bin/hermes
        if sys.platform == "win32":
            hermes_bin = VENV_DIR / "Scripts" / "hermes.exe"
        else:
            hermes_bin = VENV_DIR / "bin" / "hermes"
        if hermes_bin.exists():
            if sys.platform == "darwin":
                # Launch via Terminal.app. Previously we built one huge
                # `do script "cd '...' && export ..."` string and tried to
                # escape single quotes in SCRIPT_DIR. That's insufficient:
                # if the user ever put their HermesPortable under a path
                # containing ", `, \n or \, the injection escape hatch
                # defeated shell or AppleScript parsing and the Terminal
                # window either failed silently or ran the wrong command.
                #
                # Write a tiny driver .sh to the sandbox dir and let
                # AppleScript just `do script "bash <path>"`. The shell
                # script sees the paths as its own argv[0]'s dirname,
                # which bypasses all escaping concerns — even a path
                # containing literal double quotes survives unharmed.
                sandbox = PORTABLE_ROOT / "_home"
                sandbox.mkdir(exist_ok=True)
                driver_text = (
                    "#!/bin/bash\n"
                    # Resolve HERE from our own location, no interpolation
                    # of untrusted paths into the script body.
                    'HERE="$(cd "$(dirname "$0")/.." && pwd)"\n'
                    'cd "$HERE"\n'
                    'export HOME="$HERE/_home"\n'
                    'export HERMES_HOME="$HERE/data"\n'
                    'exec "$HERE/' + hermes_bin.relative_to(PORTABLE_ROOT).as_posix() + '" "$@"\n'
                )
                # Put the driver inside the sandbox so Terminal doesn't
                # leave a stray file on the user's real home. A fixed
                # name makes it idempotent across relaunches.
                driver_path = sandbox / ".launch-hermes.sh"
                driver_path.write_text(driver_text, encoding="utf-8")
                driver_path.chmod(0o755)
                # AppleScript only needs to see a single shell-safe
                # argument: the path to our driver. The wrapping we
                # still do here only guards against double-quote or
                # backslash in the path itself, which we write to the
                # dict of the AppleScript `do script` command. AppleScript
                # strings use backslash escaping like C.
                as_path = str(driver_path).replace("\\", "\\\\").replace('"', '\\"')
                script = (
                    'tell application "Terminal"\n'
                    '    activate\n'
                    f'    do script "bash \\"{as_path}\\""\n'
                    'end tell'
                )
                subprocess.run(["osascript", "-e", script])
            else:
                env = os.environ.copy()
                env["HERMES_HOME"] = str(DATA_DIR)
                # HOME is already sandboxed by the launcher; subprocess.Popen
                # inherits os.environ so no extra action needed here.
                if sys.platform == "win32":
                    # Inherit a proper PATH so hermes can reach venv tools,
                    # node, and the portable python. Also force UTF-8 so
                    # Chinese output doesn't blow up in the new console.
                    scripts = VENV_DIR / "Scripts"
                    node_dir = PORTABLE_ROOT / "node-windows-x64"
                    if not node_dir.exists():
                        node_dir = PORTABLE_ROOT / "node"
                    python_dir = PORTABLE_ROOT / "python-windows-x64"
                    if not python_dir.exists():
                        python_dir = PORTABLE_ROOT / "python"
                    path_parts = [str(scripts), str(node_dir), str(python_dir),
                                  env.get("PATH", "")]
                    env["PATH"] = os.pathsep.join(p for p in path_parts if p)
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    # Launch in a new console window (like macOS gets its own Terminal)
                    subprocess.Popen([str(hermes_bin)], env=env, cwd=str(PORTABLE_ROOT),
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen([str(hermes_bin)], env=env, cwd=str(PORTABLE_ROOT))

    def log_message(self, format, *args):
        pass


def main():
    os.environ["HERMES_HOME"] = str(DATA_DIR)
    env = parse_env()
    has_key = any(env.get(p["env"]) for p in PROVIDERS)
    actual_port = PORT
    server = None
    for try_port in range(PORT, PORT + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", try_port), ConfigHandler)
            actual_port = try_port
            break
        except OSError as e:
            if e.errno in (48, 98, 10048):  # macOS/Linux/Windows: address in use
                continue
            raise
    if server is None:
        print(f"  All ports {PORT}-{PORT+9} are in use. Is another Hermes already running?", file=sys.stderr)
        sys.exit(1)
    url = f"http://127.0.0.1:{actual_port}"

    # Generate Token for authentication
    SERVER_TOKEN = secrets.token_hex(32)

    # Write runtime.json for process communication
    import json
    from datetime import datetime
    runtime = {
        "configServerPort": actual_port,
        "configServerToken": SERVER_TOKEN,
        "configServerUpdatedAt": datetime.now().isoformat(),
        "pid": os.getpid()
    }
    runtime_path = DATA_DIR / "runtime.json"
    try:
        runtime_path.write_text(json.dumps(runtime, indent=2))
        os.chmod(runtime_path, 0o600)
    except Exception as e:
        print(f"  Warning: Could not write runtime.json: {e}", file=sys.stderr)

    print(f"""
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable

  Config: {url}
  Token:  {SERVER_TOKEN[:8]}...
""")

    # Only open the browser if the launcher didn't already. All four
    # launchers (Hermes.bat, Hermes.command, Hermes.sh, Hermes-WSL.bat)
    # set HERMES_BROWSER_OPENED=1 before invoking us, so double-clicking
    # Hermes.bat no longer opens two tabs at once. Fall back to opening
    # ourselves when someone runs `python config_server.py` directly.
    if not os.environ.get("HERMES_BROWSER_OPENED"):
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    if has_key:
        print("  API Key detected — ready to launch")
        print("  Or modify config and click Launch\n")
    else:
        print("  Configure your API Key in the browser\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nConfig panel closed.")
        server.server_close()


if __name__ == "__main__":
    main()
