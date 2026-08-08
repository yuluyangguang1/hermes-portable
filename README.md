# Hermes Portable

> 便携版 Hermes Agent — 零安装、单目录、U 盘即走。内置 Python / Node.js / Web UI，开箱即用。

[![GitHub Release](https://img.shields.io/github/v/release/yuluyangguang1/hermes-portable?label=release)](https://github.com/yuluyangguang1/hermes-portable/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## ✨ 特性

- 🚀 **零安装** — 解压即用，所有依赖（Python 3.12、Node.js 24、Hermes Agent、hermes-web-ui）已打包
- 📁 **单目录** — 整个运行时在一个文件夹，拷贝即迁移
- 💾 **U 盘即走** — 插上就能用，数据全在 `data/`
- 🔒 **数据隔离** — 配置、会话、历史全部存于包内 `data/`，不污染宿主 `~/.hermes`
- 🌐 **跨平台** — macOS (arm64 / x64) · Windows (x64) · Linux
- 🎛️ **配置中心** — Web 界面（:17520）管理 API Key / 模型 / 渠道，常驻后台
- 🖥️ **多模式** — 终端 CLI（默认）· Web UI（:8648）· 桌面版（Electron，可选）

---

## 📦 下载

从 [GitHub Releases](https://github.com/yuluyangguang1/hermes-portable/releases) 下载对应平台：

| 平台 | 文件 | 启动方式 |
|------|------|----------|
| macOS (Apple Silicon) | `HermesPortable-macos-arm64.zip` | 双击 `Hermes.command` |
| macOS (Intel) | `HermesPortable-macos-x64.zip` | 双击 `Hermes.command` |
| Windows (x64) | `HermesPortable-Windows-x64.zip` | 双击 `Hermes.bat` |
| Linux | 自行构建（见下） | `./Hermes.sh` |

> macOS 首次运行若被 Gatekeeper 拦截：右键 → 打开，或在终端执行一次 `xattr -cr /path/to/HermesPortable` 即可解除隔离（启动脚本也会自动处理）。

---

## 🚀 快速开始

### 1. 解压

```bash
# macOS
unzip HermesPortable-macos-x64.zip
cd HermesPortable
```

### 2. 启动

```bash
# macOS
./Hermes.command

# Windows
Hermes.bat

# Linux
./Hermes.sh
```

启动后：
- **配置中心**自动在后台常驻：`http://127.0.0.1:17520`（关掉终端也不会关闭）
- 浏览器自动打开配置中心，填入 API Key、选模型、保存
- 默认进入**终端模式**（CLI），可直接对话

### 3. 三种使用模式

| 模式 | 说明 | 如何进入 |
|------|------|----------|
| **终端 CLI** | 默认模式，终端内对话 | 直接双击启动 |
| **Web UI** | 图形界面 `http://127.0.0.1:8648` | 配置中心顶栏点「Web UI」按钮启动 |
| **桌面版** | Electron 独立窗口 | 配置中心顶栏点「桌面版」按钮（需包内含桌面运行时） |

> 桌面版运行时体积较大、需单独构建，并非每个发行包都包含。若包内无桌面版，点按钮会**明确提示**"此便携包未包含桌面版运行时"或"架构不匹配，请装 Rosetta 2"。

---

## 🎛️ 配置中心（:17520）

Web 界面管理 Hermes 配置，支持：

- ✅ **74+ LLM 提供商**：OpenRouter、Anthropic、OpenAI、DeepSeek、Google Gemini、xAI Grok、智谱 GLM、通义千问、Kimi、豆包、MiniMax、Mistral…（真实品牌 SVG 图标）
- ✅ **API Key / 模型管理**，一键快速切换模型
- ✅ **渠道配置**：Telegram、Discord、Slack、WhatsApp、WeChat、Email、Signal、Matrix
- ✅ **偏好设置、版本更新、配置导入/导出**
- ✅ **启动 Web UI / 桌面版**（顶栏按钮，点击即有反馈提示）

配置存于包内 `data/.env` 与 `data/config.yaml`，与宿主全局 `~/.hermes` 完全隔离。

---

## 📁 目录结构

```
HermesPortable/
├── Hermes.command          # macOS 启动器
├── Hermes.bat             # Windows 启动器
├── Hermes.sh              # Linux 启动器
├── lib/
│   ├── config_server.py    # 配置中心后端（:17520）
│   ├── config/
│   │   ├── index.html      # 配置中心前端
│   │   └── index-standalone.html
│   ├── chat_viewer.py
│   ├── update.py / update.sh
│   └── fix_shims.py        # 启动修复脚本
├── tools/
│   └── build.py            # 构建脚本（CI 用）
├── hermes-agent/           # Hermes Agent 源码（可编辑安装）
├── venv/                   # Python 虚拟环境（含 hermes CLI）
├── python/                 # 独立 Python 运行时（python-build-standalone）
├── node/                   # 独立 Node.js 运行时（v24 LTS）
├── runtime/desktop/        # 桌面版 Electron 运行时（可选，dist/mac 或 dist/mac-arm64）
├── data/                   # 用户数据（隔离区）
│   ├── .env                # API Keys
│   ├── config.yaml         # 模型配置
│   ├── runtime.json        # 运行时信息
│   ├── .hermes-web-ui/     # Web UI 隔离数据
│   └── desktop-userdata/   # 桌面版用户数据
├── _home/                  # 沙箱 HOME（.hermes 软链指向 data/）
├── icons/                  # 72 个品牌 SVG
├── fonts/                  # 字体（霞鹜文楷 / Tabler Icons）
├── VERSION
└── README.md
```

---

## 🛠️ 构建（开发者）

```bash
# 构建当前平台发行包
python3 tools/build.py

# 指定平台
python3 tools/build.py --platform macos-arm64
python3 tools/build.py --platform macos-x64
python3 tools/build.py --platform windows-x64

# 本地验证配置中心
python3 lib/config_server.py
```

CI 工作流（`.github/workflows/`）：
- `build.yml` — 按平台构建并发布 Release
- `build-universal.yml` — 合并多平台 zip 并创建 Release

> 构建会自动下载并打包 Python / Node.js / hermes-web-ui，并对 `python3`、`node`、`npm` 做可执行权限与启动验证，避免发布坏包。

---

## 🐛 已知限制

- **Windows 包**：当前 CI 的 Windows runner 存在网络/DNS 偶发故障（EAI_FAIL），Windows 包可能暂未随 Mac 包同步发布。Windows 用户可本地 `tools/build.py --platform windows-x64` 自行构建。
- **桌面版架构**：macOS 发行包内的桌面版 App 为单一架构（arm64 或 x64）。在相反架构的 Mac 上点「桌面版」按钮会提示"架构不匹配，请安装 Rosetta 2 或下载对应架构包"。
- **Node 版本**：macOS / Linux 用 Node.js 24 LTS；Windows 因 CI runner 的已知崩溃暂用 22 LTS。两者均兼容 hermes-web-ui。

---

## 📝 更新日志（近期）

完整历史见 [CHANGELOG.md](CHANGELOG.md) 与 [Releases](https://github.com/yuluyangguang1/hermes-portable/releases)。

### v1.20.x 关键修复
- **v1.20.15** — 配置中心新增「桌面版」启动按钮（含架构检查与提示）；默认启动模式改回终端 CLI
- **v1.20.14** — macOS / Linux Node.js 升回 24 LTS（满足 24+ 预期）
- **v1.20.13** — Web UI 强制使用包内 Node.js（不再静默回退系统 Node）
- **v1.20.12** — Web UI 真正启动（修复 `node/package.json` 与 server 路径）+ 配置中心常驻（关终端不关闭）
- **v1.20.11** — 修复 editable finder 路径计算（`hermes_cli` 找不到导致 Hermes 网关起不来）
- **v1.20.9 / v1.20.10** — 修复启动脚本 `set -u` 变量未定义、Node 版本判断、shim 路径

---

## 🔗 相关链接

- [Hermes Agent 官方](https://hermes-agent.nousresearch.com/)
- [GitHub 仓库](https://github.com/yuluyangguang1/hermes-portable)
- [问题反馈](https://github.com/yuluyangguang1/hermes-portable/issues)

## 📄 许可证

MIT License

## 🙏 致谢

- [Hermes Agent](https://hermes-agent.nousresearch.com/) — Nous Research
- [Tabler Icons](https://tabler-icons.io/) — 图标库
- [LXGW WenKai](https://github.com/lxgw/LxgwWenKai) — 字体
