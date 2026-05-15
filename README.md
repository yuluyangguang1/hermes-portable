# 🚀 Hermes Portable

> Plug-in-a-USB [Hermes Agent](https://github.com/NousResearch/hermes-agent) · zero-install, zero-trace, cross-platform
> 插上U盘即用的 AI Agent · 零安装、零痕迹、全平台

[![Release](https://img.shields.io/github/v/release/yuluyangguang1/hermes-portable?label=release)](https://github.com/yuluyangguang1/hermes-portable/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](#支持平台)

**Build once, run anywhere** — everything bundled (Python, Node.js, venv, agent source, Web UI). Stick it on a USB, double-click, go. The host machine's `~/.hermes/`, `$PATH`, registry, nothing gets touched.

---

## ✨ 特性

- **零安装** — Python / Node 运行时自带，不依赖系统任何东西
- **零痕迹** — 所有读写劫持到 U 盘 `data/` 目录，宿主机零接触
- **三平台原生** — macOS（arm64/x64）、Linux（x64/arm64）、Windows（x64）
- **Universal 包** — 单个 zip 带齐三平台 venv，启动器自动识别
- **自我成长** — 持久记忆 + 自动生成技能，运行越久越强（官方核心特性）
- **多平台接入** — Telegram/Discord/Slack/WhatsApp/Signal/Email/CLI，一处启动多处可达
- **定时自动化** — 自然语言 cron 调度，无人值守执行报告/备份/简报
- **子代理委派** — 隔离子对话 + 独立终端 + Python RPC，零上下文成本流水线
- **沙箱隔离** — 本地/Docker/SSH/Singularity/Modal 五种后端
- **可视化配置中心** — 选模型/填 Key/测试连接/换模型/查看日志/导入导出
- **自动更新** — 支持 git 用户和 release zip 用户两种更新模式

## 支持平台

| 平台 | 启动器 | 要求 |
|------|--------|------|
| **macOS** | 双击 `Hermes.command` | macOS 10.15+ (Intel / Apple Silicon) |
| **Linux** | `./Hermes.sh` | glibc 2.28+（Node.js 22 要求） |
| **Windows** | 双击 `Hermes.bat` | Windows 10 / 11（原生，无需 WSL） |

> Windows 原生仍是 **Early Beta**。遇到问题可以 fallback 到 `Hermes-WSL.bat`（需要 WSL2 + Ubuntu）。

---

## 🚀 快速开始

### 方式一：下载预构建包（推荐）

从 [Releases](https://github.com/yuluyangguang1/hermes-portable/releases/latest) 选一个：

| 包 | 适用 | 大小 |
|----|------|------|
| `HermesPortable-Universal.zip` | 一包三平台，U 盘多机用 | ~600 MB |
| `HermesPortable-macOS.zip` | 仅 macOS | ~250 MB |
| `HermesPortable-Linux.zip` | 仅 Linux | ~420 MB |
| `HermesPortable-Windows.zip` | 仅 Windows | ~80 MB |

下载 → 解压 → 双击启动器。首次运行会在浏览器打开配置面板（`http://127.0.0.1:17520`），填 API Key 即可。

### 方式二：本地构建

```bash
git clone https://github.com/yuluyangguang1/hermes-portable.git
cd hermes-portable

# 平台单包
python3 build.py                    # → dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # → 直接落到 U 盘

# Universal 多平台（见下一节）
python3 build.py --layout universal
```

Windows 上一样是 `python build.py`，**不再有** `build_windows.py`（已合并进 `build.py`）。

**要求：** Python 3.8+、`git`、`curl`。

> 📖 完全不懂命令行？项目根目录的 [`构建教程.html`](构建教程.html) 是零基础图文版。

### 方式三：Universal 多平台包

在每台目标机器上各构建一次，合并成一个"三合一"的 Universal 包（启动器自动识别当前系统）。

```bash
# 每台机器各跑一次，输出到同一个共享目录
# macOS:
python3 build.py --layout universal --output /path/to/shared
# Linux:
python3 build.py --layout universal --output /path/to/shared
# Windows:
python build.py --layout universal --output X:\path\to\shared
```

`--layout universal` 会把 venv/python/node 放进 `venv-<platform>/`、`python-<platform>/`、`node-<platform>/` 子目录，三平台产物互不冲突，可以直接合并。

> GitHub Actions 的 `Build Universal` workflow 就是自动化这一步，每次打 tag 自动出 Universal 包。

---

## 使用

1. 解压到 U 盘或任意目录（**避免深路径**：Windows 有 260 字符限制）
2. 双击启动器：
   - macOS → `Hermes.command`
   - Windows → `Hermes.bat`
   - Linux → `./Hermes.sh`
3. 首次启动自动打开 `http://127.0.0.1:17520`，填 API Key → 保存 → 启动

后续启动时配置中心也会在后台运行，浏览器打开 `http://127.0.0.1:17520` 可随时换模型、查看日志、检查更新。

就这样。**不动宿主机任何文件**。

## 配置中心功能

启动后访问 `http://127.0.0.1:17520`：

| 区域 | 功能 |
|------|------|
| 顶部状态栏 | Hermes 进程运行状态（绿点 + PID）、Web UI 快捷入口 |
| 模型 标签页 | 选提供商、填 API Key、测试连接、选模型 |
| 渠道 标签页 | 配置 Telegram/Discord/Slack/WhatsApp/微信/邮件等 |
| 设置 标签页 | 上下文压缩、显示费用、工具进度、持久记忆 |
| 配置管理 | 导出/导入/查看 .env/重置 |
| 运行日志 | 查看最近 200 行 Hermes 日志 |
| 检查更新 | git 模式 + release 模式双更新通道 |
| 启动/重启 | 一键启动 Hermes，运行中支持重启 |

## 零痕迹保证

启动器会在 U 盘内创建一个沙箱 HOME：

```
HermesPortable/
├── _home/              ← 沙箱 HOME（启动时自动建）
│   └── .hermes/        ← symlink / junction → data/
├── data/               ← 实际用户数据都在这里
├── venv-<platform>/
├── python-<platform>/
└── node-<platform>/
```

进程启动前：
- Unix: `export HOME=$HERE/_home`
- Windows: `set HOME=%HERE%\_home` + `set USERPROFILE=%HERE%\_home`

于是所有走 `~/.hermes` 的读写（hermes-web-ui 缓存、pip config、Node 的 npm/npx 等）**全部落到 U 盘内的 `data/` 里**，宿主机真 `~/.hermes/`、`%USERPROFILE%\.hermes` 从头到尾**零接触**。

拔掉 U 盘 → 什么都带走，什么都没留下。

## 目录结构

```
HermesPortable/
├── Hermes.command / .sh / .bat / -WSL.bat    # 各平台启动器
├── _home/                                     # HOME 沙箱（启动时自动生成）
├── data/                                      # 用户数据（唯一需要备份的）
│   ├── .env                                   # API Keys
│   ├── config.yaml                            # 模型/渠道配置
│   ├── sessions/ skills/ memories/ …
├── venv-<platform>/                           # Python 虚拟环境
├── python-<platform>/                         # 独立 Python 3.12 运行时
├── node-<platform>/                           # Node.js + hermes-web-ui
├── hermes-agent/                              # 上游源码（可 git pull 更新）
├── config_server.py                           # 配置面板
├── chat_viewer.py                             # 聊天记录查看器
├── update.py                                  # 自更新
└── README.txt / guide.html / …                # 文档
```

## 为什么用 Hermes Portable？

| 对比 | 官方安装 | Hermes Portable |
|------|---------|-----------------|
| 安装 | `curl \| bash` + 配置 | 双击启动器 |
| 系统影响 | 写 `~/.hermes/`、注册全局命令 | 完全零写入，零注册 |
| 换电脑 | 重装 + 迁移数据 | 拔 U 盘，插到下一台 |
| Python/Node | 依赖系统或用 nvm/pyenv | 全部自带 |
| 离线场景 | ❌ 需要联网安装 | ✅ 首次构建后可离线用 |
| 多设备同步 | 手动同步 | 数据跟着 U 盘走 |

## Web 管理界面

启动后自动在后台起 [hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui)，默认端口 `8648`。

### 端口占用

| 服务 | 端口 | 用途 |
|------|------|------|
| Hermes Agent Gateway | 8642 | 内部 API |
| Hermes Web UI | 8648 | 浏览器管理界面 |
| Config Panel | 17520 | 首次配置 + 模型/渠道面板 |
| Chat Viewer | 17521 | 会话浏览 |

## 备份与更新

- **备份**：只复制 `data/`
- **更新**：配置面板 → 底部「检查更新」→「更新到最新版」
- **命令行更新**：`python update.py update`

## 相关链接

| 项目 | 作用 |
|------|------|
| [hermes-portable](https://github.com/yuluyangguang1/hermes-portable) | 本项目 |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 上游（Nous Research 的自进化 AI Agent） |
| [hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui) | Web 管理界面 |
| [官方文档](https://hermes-agent.nousresearch.com/docs) | Hermes Agent docs |

## 致谢

- [Nous Research](https://nousresearch.com) — Hermes Agent
- [EKKOLearnAI](https://github.com/EKKOLearnAI) — hermes-web-ui
- [astral-sh/uv](https://github.com/astral-sh/uv) — 包管理 + 独立 Python
- [Node.js](https://nodejs.org) — Web UI 运行时

## License

[MIT](LICENSE) · 与上游 hermes-agent 许可一致。
