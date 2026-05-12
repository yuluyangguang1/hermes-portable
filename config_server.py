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
import webbrowser
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"


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

    for candidate in (SCRIPT_DIR / f"venv-{label}", SCRIPT_DIR / "venv"):
        py = (candidate / "Scripts" / "python.exe") if system == "Windows" \
            else (candidate / "bin" / "python")
        if py.exists():
            return candidate
    # Fallback: return the single-platform default even if missing,
    # so downstream error messages stay informative.
    return SCRIPT_DIR / "venv"


VENV_DIR = _detect_venv_dir()
ENV_FILE = DATA_DIR / ".env"
CONFIG_FILE = DATA_DIR / "config.yaml"

PORT = 17520

# ═══════════════════════════════════════════════════════════════
#  DATA DEFINITIONS
# ═══════════════════════════════════════════════════════════════

PROVIDERS = [
    {"id": "openrouter",  "name": "OpenRouter",     "env": "OPENROUTER_API_KEY", "models": ["anthropic/claude-sonnet-4", "anthropic/claude-opus-4-6", "openai/gpt-4o", "google/gemini-2.5-pro", "deepseek/deepseek-chat-v3"]},
    {"id": "anthropic",   "name": "Anthropic",      "env": "ANTHROPIC_API_KEY",  "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"]},
    {"id": "openai",      "name": "OpenAI",         "env": "OPENAI_API_KEY",     "models": ["gpt-4o", "gpt-4.1", "o3-mini"]},
    {"id": "deepseek",    "name": "DeepSeek",       "env": "DEEPSEEK_API_KEY",   "models": ["deepseek-chat", "deepseek-reasoner"]},
    {"id": "google",      "name": "Google Gemini",  "env": "GOOGLE_API_KEY",     "models": ["gemini-2.5-pro", "gemini-2.5-flash"]},
    {"id": "xiaomi",      "name": "Xiaomi MiMo",    "env": "XIAOMI_API_KEY",     "models": ["xiaomi/mimo-v2-pro", "xiaomi/mimo-v2-flash"]},
    {"id": "nous",        "name": "Nous Portal",    "env": "NOUS_API_KEY",       "models": ["nousresearch/hermes-4-405b", "nousresearch/deephermes-3-mistral-24b"]},
    {"id": "kimi",        "name": "Kimi / Moonshot","env": "KIMI_API_KEY",       "models": ["kimi-k2-0711-preview", "moonshot-v1-128k"]},
    {"id": "dashscope",   "name": "Alibaba DashScope","env": "DASHSCOPE_API_KEY","models": ["qwen-max", "qwen-plus"]},
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
#  CONFIG READ/WRITE
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
    active_provider = "openrouter"
    for p in PROVIDERS:
        if env.get(p["env"]):
            active_provider = p["id"]
            break
    return {
        "env": env,
        "config": cfg,
        "providers": PROVIDERS,
        "channels": CHANNELS,
        "active_provider": active_provider,
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


def save_config(data):
    # Input validation: sanitize env keys to prevent injection
    import re
    valid_env_keys = {p["env"] for p in PROVIDERS}
    for ch in CHANNELS:
        for field in ch["fields"]:
            valid_env_keys.add(field["key"])

    lines = []
    lines.append("# ═══════════════════════════════════════════")
    lines.append("#  Hermes Portable — Environment Variables")
    lines.append("# ═══════════════════════════════════════════")
    lines.append("")
    lines.append("# ── LLM Provider API Keys ──")
    for p in PROVIDERS:
        val = data.get("env", {}).get(p["env"], "")
        if val:
            # Strip newlines to prevent env injection
            val = str(val).replace("\n", "").replace("\r", "")
            lines.append(f"{p['env']}={val}")
        else:
            lines.append(f"# {p['env']}=")
    lines.append("")
    lines.append("# ── Messaging Channel Tokens ──")
    for ch in CHANNELS:
        for field in ch["fields"]:
            val = data.get("env", {}).get(field["key"], "")
            if val:
                val = str(val).replace("\n", "").replace("\r", "")
                lines.append(f"{field['key']}={val}")
            else:
                lines.append(f"# {field['key']}=")
    lines.append("")
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")

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

    CONFIG_FILE.write_text("\n".join(_yaml_dump_simple(cfg)) + "\n", encoding="utf-8")
    return True

# ═══════════════════════════════════════════════════════════════
#  HTML — matching Hermes Web UI style (port 9119)
# ═══════════════════════════════════════════════════════════════

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Portable — 配置</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
  /* Google Fonts removed for China compatibility */

  :root {
    --bg: #041c1c;
    --card: #062424;
    --secondary: #0a2e2e;
    --muted: #083030;
    --fg: #ffe6cb;
    --fg-muted: #8aaa9a;
    --border: #ffe6cb26;
    --accent: #ffe6cb;
    --emerald: oklch(0.765 0.177 163.223);
    --emerald-dim: oklch(0.696 0.17 162.48);
    --blue: oklch(0.707 0.165 254.624);
    --purple: oklch(0.714 0.203 305.504);
    --warning: #ffbd38;
    --success: #4ade80;
    --destructive: #fb2c36;
    --font-sans: 'Mondwest', Arial, sans-serif;
    --font-mono: 'Courier Prime', 'Courier New', monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--fg);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    scrollbar-color: #ffe6cb33 transparent;
    position: relative;
  }

  /* warm glow overlay like 9119 */
  body::before {
    content: '';
    position: fixed; inset: 0;
    pointer-events: none; z-index: 99;
    mix-blend-mode: lighten;
    opacity: 0.22;
    background: radial-gradient(at 0 0, #ffbd3859, transparent 60%);
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
    font-size: 11px;
    color: var(--fg-muted);
    letter-spacing: 0.08em;
    margin-top: 4px;
  }

  /* Section labels like 9119 */
  .section-label {
    font-family: var(--font-sans);
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--fg-muted);
    margin-bottom: 8px;
    padding-left: 2px;
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
    font-size: 11px;
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
    font-size: 10px;
    letter-spacing: 0.05em;
    cursor: pointer;
    text-align: center;
    transition: all 0.15s;
  }
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
    font-size: 10px;
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
    font-size: 10px;
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
    font-size: 10px;
    color: var(--fg-muted);
  }
  .channel-status {
    font-family: var(--font-mono);
    font-size: 9px;
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
    font-size: 10px;
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
    padding: 12px 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.15s;
    text-align: center;
    font-weight: 700;
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
    font-size: 11px;
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
    font-size: 9px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--fg-muted);
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #ffe6cb26; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #ffe6cb40; }

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
    font-size: 11px;
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
    font-size: 11px;
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
    font-size: 10px; color: var(--emerald);
    flex-shrink: 0;
    margin-top: -1px;
  }
  .step-num.active {
    background: var(--emerald-dim);
    border-color: var(--emerald);
    color: var(--bg);
  }
  .onboarding-card .btn { margin-top: 8px; }
</style>
</head>
<body>
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
    <button class="btn btn-launch" style="width:100%;margin-top:12px" onclick="dismissOnboarding()">
      开始配置
    </button>
  </div>
</div>

<div class="container">
  <div class="header">
    <svg class="logo" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <g fill="#ffe6cb">
        <!-- Petasos Hat -->
        <path d="M 28 22 Q 28 4, 50 4 Q 72 4, 72 22"/>
        <ellipse cx="50" cy="22" rx="34" ry="7"/>
        <path d="M 36 12 Q 36 6, 50 6 Q 56 6, 58 10 L 52 14 Z" fill="#041c1c" opacity="0.15"/>
        <!-- Wings -->
        <path d="M 22 22 C 12 12, 2 14, 4 22 C 5 28, 12 30, 18 28 C 14 30, 8 28, 8 24 C 8 20, 14 18, 22 22 Z"/>
        <path d="M 78 22 C 88 12, 98 14, 96 22 C 95 28, 88 30, 82 28 C 86 30, 92 28, 92 24 C 92 20, 86 18, 78 22 Z"/>
        <path d="M 20 20 C 14 14, 6 16, 8 22 L 14 22 Z" fill="#041c1c" opacity="0.12"/>
        <path d="M 80 20 C 86 14, 94 16, 92 22 L 86 22 Z" fill="#041c1c" opacity="0.12"/>
        <!-- Face -->
        <ellipse cx="50" cy="50" rx="22" ry="24"/>
        <!-- Eyes -->
        <ellipse cx="41" cy="46" rx="6" ry="7" fill="#041c1c"/>
        <circle cx="42" cy="46" r="3.5" fill="#ffe6cb"/>
        <circle cx="43" cy="44" r="1.3" fill="#041c1c"/>
        <circle cx="40" cy="47" r="0.6" fill="#041c1c" opacity="0.4"/>
        <ellipse cx="59" cy="46" rx="6" ry="7" fill="#041c1c"/>
        <circle cx="58" cy="46" r="3.5" fill="#ffe6cb"/>
        <circle cx="59" cy="44" r="1.3" fill="#041c1c"/>
        <circle cx="56" cy="47" r="0.6" fill="#041c1c" opacity="0.4"/>
        <!-- Eyebrows -->
        <path d="M 34 38 Q 41 34, 48 38" fill="none" stroke="#041c1c" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M 52 38 Q 59 34, 66 38" fill="none" stroke="#041c1c" stroke-width="1.8" stroke-linecap="round"/>
        <!-- Nose -->
        <path d="M 50 50 L 48 56" fill="none" stroke="#041c1c" stroke-width="1.2" stroke-linecap="round" opacity="0.5"/>
        <!-- Mouth -->
        <path d="M 43 62 Q 50 67, 57 62" fill="none" stroke="#041c1c" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M 46 62 L 54 62" fill="none" stroke="#041c1c" stroke-width="0.6" opacity="0.3"/>
        <!-- Cheek highlights -->
        <ellipse cx="35" cy="56" rx="4" ry="2.5" fill="#041c1c" opacity="0.06"/>
        <ellipse cx="65" cy="56" rx="4" ry="2.5" fill="#041c1c" opacity="0.06"/>
        <!-- Face shine -->
        <ellipse cx="56" cy="38" rx="7" ry="12" fill="#041c1c" opacity="0.08"/>
        <!-- USB Pendant -->
        <line x1="68" y1="54" x2="72" y2="62" stroke="#ffe6cb" stroke-width="2"/>
        <rect x="68" y="62" width="8" height="10" rx="1.5"/>
        <rect x="70" y="58" width="4" height="6" rx="1"/>
        <rect x="69" y="63" width="2" height="7" rx="1" fill="#041c1c" opacity="0.35"/>
      </g>
    </svg>
    <h1>Hermes Portable</h1>
    <div class="subtitle">配置你的 AI 代理</div>
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
          <button type="button" class="btn btn-launch" style="width:100%" onclick="runUpdate()">
            更新到最新版
          </button>
        </div>
        <div id="updateLog" style="margin-top:8px;font-family:var(--font-mono);font-size:10px;color:var(--emerald);display:none;white-space:pre-wrap;"></div>
      </div>
    </div>

    <div class="actions">
      <button type="button" class="btn btn-save" onclick="saveConfig()">保存</button>
      <button type="button" class="btn btn-launch" id="launchBtn" onclick="launchHermes()">启动</button>
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
  const g = document.getElementById('providerGrid');
  g.innerHTML = PROVIDERS.map(p => `
    <button type="button" class="provider-btn ${p.id===activeProvider?'active':''}"
            onclick="selectProvider('${p.id}')">${p.name}</button>`).join('');
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
        ${ch.fields.map(f => `<div class="field">
          <label>${f.label}</label>
          <input type="${f.type}" placeholder="${f.placeholder}"
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
    if (data.update_available && data.has_git) {
      action.style.display = 'block';
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

init();
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


class ConfigHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_html()
        elif self.path == "/favicon.svg":
            self._serve_favicon()
        elif self.path == "/api/config":
            self._json_response(read_config())
        elif self.path == "/api/version":
            self._json_response(self._get_version())
        else:
            self.send_error(404)

    def do_POST(self):
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
        favicon_path = SCRIPT_DIR / "favicon.svg"
        if favicon_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.end_headers()
            self.wfile.write(favicon_path.read_bytes())
        else:
            self.send_error(404)

    def _json_response(self, data):
        self.send_response(200)
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
        has_git = (SCRIPT_DIR / "hermes-agent" / ".git").exists()
        return {
            "local": local,
            "remote": remote,
            "has_git": has_git,
            "update_available": (
                "date" in remote
                and "20" in str(local)
                and remote.get("date", "") > _extract_date(local)
            ) if has_git else False,
        }

    def _run_update(self):
        update_script = SCRIPT_DIR / "update.py"
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
                           cwd=str(SCRIPT_DIR))
        except Exception:
            pass

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
                "body": json.dumps({"model": model or "claude-sonnet-4-20250514", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}).encode(),
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
        }

        cfg = PROVIDER_CONFIGS.get(provider_id)
        if not cfg:
            return {"success": False, "error": f"Unknown provider: {provider_id}"}

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
                # Escape single quotes in paths to prevent AppleScript injection
                safe_dir = str(SCRIPT_DIR).replace("'", "'\\''")
                safe_home = str(DATA_DIR).replace("'", "'\\''")
                safe_bin = str(hermes_bin).replace("'", "'\\''")
                # AppleScript `do script` opens a *fresh* login shell, so we
                # must re-apply the HOME hijack (sandbox = SCRIPT_DIR/_home).
                # Otherwise hermes reads the host's real ~/.hermes, breaking
                # the zero-trace promise.
                safe_sandbox = str(SCRIPT_DIR / "_home").replace("'", "'\\''")
                script = f'''tell application "Terminal"
                    activate
                    do script "cd '{safe_dir}' && export HOME='{safe_sandbox}' && export HERMES_HOME='{safe_home}' && '{safe_bin}'"
                end tell'''
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
                    node_dir = SCRIPT_DIR / "node-windows-x64"
                    if not node_dir.exists():
                        node_dir = SCRIPT_DIR / "node"
                    python_dir = SCRIPT_DIR / "python-windows-x64"
                    if not python_dir.exists():
                        python_dir = SCRIPT_DIR / "python"
                    path_parts = [str(scripts), str(node_dir), str(python_dir),
                                  env.get("PATH", "")]
                    env["PATH"] = os.pathsep.join(p for p in path_parts if p)
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    # Launch in a new console window (like macOS gets its own Terminal)
                    subprocess.Popen([str(hermes_bin)], env=env, cwd=str(SCRIPT_DIR),
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen([str(hermes_bin)], env=env, cwd=str(SCRIPT_DIR))

    def log_message(self, format, *args):
        pass


def main():
    os.environ["HERMES_HOME"] = str(DATA_DIR)
    env = parse_env()
    has_key = any(env.get(p["env"]) for p in PROVIDERS)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ConfigHandler)
    url = f"http://127.0.0.1:{PORT}"

    print(f"""
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable

  Config: {url}
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
