# 🚀 Hermes Portable

**构建一次，到处使用** — 一个完全自包含的 AI Agent，插上U盘直接运行。

> 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent)（Nous Research）打造的便携版本。

## 支持平台

| 平台 | 启动器 | 要求 |
|------|--------|------|
| **macOS** | `Hermes.command` 双击 | macOS 10.15+ |
| **Linux** | `./Hermes.sh` 终端运行 | glibc 2.17+ |
| **Windows** | `Hermes.bat` 双击 | Windows 10/11（原生支持，Early Beta） |

> 💡 **Windows 用户**：Hermes Agent 已支持原生 Windows 运行（Early Beta），无需 WSL2。
> 如果遇到兼容性问题，可使用 `Hermes-WSL.bat` 通过 WSL2 运行作为备选方案。
> 详见 [官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)。

## 快速开始

### 方式一：下载预构建包（推荐）

从 [Releases](https://github.com/yuluyangguang1/hermes-portable/releases) 下载：

| 包 | 说明 | 大小 |
|----|------|------|
| `HermesPortable-Universal.zip` | 多平台合一（macOS + Linux + Windows） | ~600MB |
| `HermesPortable-macOS.zip` | 仅 macOS | ~210MB |
| `HermesPortable-Linux.zip` | 仅 Linux | ~210MB |
| `HermesPortable-Windows.zip` | 仅 Windows | ~210MB |

下载后解压，双击启动器即可：
- **macOS** → `Hermes.command`
- **Windows** → `Hermes.bat`
- **Linux** → `./Hermes.sh`

首次使用会自动打开配置面板，填入 API Key 即可。

### 方式二：本地构建

每个平台需要在对应系统上构建（Python C 扩展是平台特定的）。

#### macOS / Linux
```bash
git clone https://github.com/yuluyangguang1/hermes-portable.git
cd hermes-portable
python3 build.py                    # 输出到 dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # 直接输出到U盘
```

#### Windows
```bash
git clone https://github.com/yuluyangguang1/hermes-portable.git
cd hermes-portable
python build_windows.py             # 输出到 dist/HermesPortable/
```

**构建环境要求：** Python 3.8+、git、curl

> 📖 完全不懂命令行？请看 [构建教程.html](构建教程.html)（项目根目录），手把手教你从零开始。

### 方式三：本地多平台合并

如果你有多台不同系统的电脑，可以分别构建后合并成 Universal 包：

```bash
# 1. 在每台电脑上构建到不同目录
# Mac:
python3 build.py /path/to/HermesPortable-mac
# Linux:
python3 build.py /path/to/HermesPortable-linux
# Windows:
python build_windows.py D:\HermesPortable-win

# 2. 在一台电脑上合并
mkdir HermesPortable-Universal

# 复制共享文件（从任一平台）
cp -r /path/to/HermesPortable-mac/hermes-agent HermesPortable-Universal/
cp -r /path/to/HermesPortable-mac/node HermesPortable-Universal/
cp -r /path/to/HermesPortable-mac/data HermesPortable-Universal/
cp /path/to/HermesPortable-mac/*.command HermesPortable-Universal/
cp /path/to/HermesPortable-mac/*.sh HermesPortable-Universal/
cp /path/to/HermesPortable-mac/*.html HermesPortable-Universal/
cp /path/to/HermesPortable-mac/config_server.py HermesPortable-Universal/
cp /path/to/HermesPortable-mac/chat_viewer.py HermesPortable-Universal/
cp /path/to/HermesPortable-mac/update.py HermesPortable-Universal/

# 重命名各平台 venv + python
mv /path/to/HermesPortable-mac/venv HermesPortable-Universal/venv-macos-arm64
mv /path/to/HermesPortable-mac/python HermesPortable-Universal/python-macos-arm64
mv /path/to/HermesPortable-linux/venv HermesPortable-Universal/venv-linux-x64
mv /path/to/HermesPortable-linux/python HermesPortable-Universal/python-linux-x64
mv /path/to/HermesPortable-win/venv HermesPortable-Universal/venv-windows-x64
mv /path/to/HermesPortable-win/python HermesPortable-Universal/python-windows-x64

# 复制 Windows 启动器
cp /path/to/HermesPortable-win/*.bat HermesPortable-Universal/
```

合并后的包可以在任意平台直接使用，启动器会自动检测并选择对应的 venv。

## 使用

1. 插上U盘（或解压到任意目录）
2. 双击启动：
   - **macOS** → `Hermes.command`
   - **Windows** → `Hermes.bat`（原生运行，无需 WSL2）
   - **Linux** → `./Hermes.sh`
3. 首次使用会自动打开配置面板，填入 API Key 即可

**零安装，零依赖，不碰宿主机系统。**

## 目录结构

```
HermesPortable/
├── Hermes.command              # macOS 启动器 (双击)
├── Hermes.bat                  # Windows 启动器 (双击，原生运行)
├── Hermes-WSL.bat              # Windows WSL2 备选启动器
├── Hermes.sh                   # Linux 启动器
├── README.md                   # 本文档
├── README.txt                  # 用户指南
├── HermesPortable使用说明.html  # 中文详细说明
├── guide.html                  # 英文详细说明
├── python/                     # Python 独立运行时（单平台包）
├── python-macos-arm64/         # macOS Python（Universal 包）
├── python-linux-x64/           # Linux Python（Universal 包）
├── python-windows-x64/         # Windows Python（Universal 包）
├── venv/                       # 虚拟环境（单平台包）
├── venv-macos-arm64/           # macOS 虚拟环境（Universal 包）
├── venv-linux-x64/             # Linux 虚拟环境（Universal 包）
├── venv-windows-x64/           # Windows 虚拟环境（Universal 包）
├── hermes-agent/               # Hermes 源代码
├── node/                       # Node.js + hermes-web-ui
├── config_server.py            # Web 配置面板
├── chat_viewer.py              # 聊天记录查看器
├── update.py                   # 自动更新模块
└── data/                       # 用户数据 (配置/会话/技能/记忆)
    ├── .env                    # API Keys ← 唯一需要编辑的文件
    ├── config.yaml             # 配置
    ├── sessions/               # 对话历史
    ├── skills/                 # 技能
    └── ...
```

## 技术细节

- **Python 运行时**：通过 `uv` 下载独立的 CPython 3.12，不依赖系统 Python
- **依赖管理**：`uv` 创建 venv + 安装所有 hermes-agent 依赖
- **数据隔离**：启动脚本设置 `HERMES_HOME=data/`，所有数据存U盘
- **跨平台启动器**：
  - `.command` = macOS Finder 可双击的 shell 脚本
  - `.bat` = Windows 原生启动器（Early Beta，另有 `.bat` WSL2 备选）
  - `.sh` = Linux 终端启动器
- **Universal 包**：启动器自动检测当前平台，选择对应的 venv 目录

## 为什么选择 Hermes Portable？

即使 Hermes Agent 官方提供了安装脚本，Portable 版仍有独特价值：

| 对比项 | 官方安装 | Hermes Portable |
|--------|---------|----------------|
| 安装步骤 | `curl \| bash` + 配置 | 插U盘，双击 |
| 系统影响 | 写入 `~/.hermes/`，安装全局命令 | 零痕迹，数据全在U盘 |
| 换电脑 | 重新安装 + 迁移数据 | 拔了插上，直接用 |
| Python/Node | 依赖系统或额外安装 | 全部自包含 |
| 多设备同步 | 手动迁移 | 带着U盘就行 |

## Web 管理界面

Hermes Portable 自动集成 [hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui) —— 启动时自动在后台启动并打开浏览器。

**功能：** AI 聊天、会话管理、定时任务、用量统计、平台通道配置、技能浏览等。

**首次构建需联网：** 构建脚本会自动下载 Node.js v22 并安装 hermes-web-ui，无需手动操作。

### 端口对照

| 服务 | 端口 | 说明 |
|------|------|------|
| Hermes Agent Gateway | 8642 | 内部 API 服务 |
| Hermes Web UI | 8648 | 浏览器管理界面（可选） |
| Config Panel | 17520 | 本地配置服务器 |
| Chat Viewer | 17521 | 聊天记录查看器 |

## 备份与更新

- **备份**：只复制 `data/` 目录
- **更新 Hermes**：
  - 启动配置面板（首次启动自动打开，或删除 `data/.env` 后重启）
  - 点击「检查更新」按钮

## 相关链接

| 项目 | 说明 |
|------|------|
| [hermes-portable](https://github.com/yuluyangguang1/hermes-portable) | 本项目 — 便携版 Hermes |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | 上游项目 — Nous Research 出品的自进化 AI Agent |
| [hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui) | Web 管理界面 — 聊天/会话/定时任务/用量统计/通道配置 |
| [官方文档](https://hermes-agent.nousresearch.com/docs) | Hermes Agent 官方文档 |

## 致谢

- [Nous Research](https://nousresearch.com) — Hermes Agent 核心开发
- [EKKOLearnAI](https://github.com/EKKOLearnAI) — hermes-web-ui Web 管理界面
- [astral-sh](https://github.com/astral-sh/uv) — uv 包管理器
- [Node.js](https://nodejs.org) — hermes-web-ui 运行时

---

*最后更新: 2026-05-09*
