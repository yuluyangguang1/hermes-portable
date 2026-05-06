# 🚀 Hermes Portable

**构建一次，到处使用** — 一个完全自包含的 AI Agent，插上U盘直接运行。

## 支持平台

| 平台 | 启动器 | 要求 |
|------|--------|------|
| **macOS** | `Hermes.command` 双击 | macOS 10.15+ |
| **Linux** | `./Hermes.sh` 终端运行 | glibc 2.17+ |
| **Windows** | `Hermes.bat` 双击 | **需要 WSL**（Windows Subsystem for Linux） |

> ⚠️ **Windows 用户注意**：当前版本的 Windows 启动器依赖 WSL。请先安装 WSL：
> 1. 以管理员身份打开 PowerShell
> 2. 运行：`wsl --install`
> 3. 重启电脑
> 4. 详情：https://learn.microsoft.com/wsl/install

## 构建

### macOS / Linux（在 Mac 或 Linux 上构建）

```bash
python3 build.py                    # 输出到 dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # 直接输出到U盘
```

### Windows（在 Windows 上构建）

```powershell
# 1. 克隆或下载本项目
git clone https://github.com/yuluyangguang1/hermes-portable.git
cd hermes-portable

# 2. 运行 Windows 专用构建脚本
python build_windows.py

# 输出到 dist/HermesPortable/
# 双击 Hermes.bat 即可启动（需要 WSL）
```

**构建环境要求：** Python 3.8+、git、curl

**构建产物：** ~500MB 的完全自包含文件夹

## 使用（拿到U盘后直接用）

1. 插上U盘
2. 双击启动：
   - **macOS** → `Hermes.command`
   - **Windows** → `Hermes.bat`（需要 WSL）
   - **Linux** → `./Hermes.sh`
3. 首次使用会自动打开配置面板，填入 API Key 即可

**零安装，零依赖，不碰宿主机系统。**

## 目录结构

```
HermesPortable/
├── Hermes.command     # macOS 启动器 (双击)
├── Hermes.bat         # Windows 启动器 (双击) ← 需要 WSL
├── Hermes.sh          # Linux 启动器
├── README.md          # 本文档
├── README.txt         # 用户指南
├── python/            # Python 独立运行时（平台特定）
├── venv/              # 虚拟环境 + 所有依赖（平台特定）
├── hermes-agent/      # Hermes 源代码
├── config_server.py   # Web 配置面板
├── chat_viewer.py     # 聊天记录查看器
├── update.py          # 自动更新模块
├── uv                 # 包管理器
└── data/              # 用户数据 (配置/会话/技能/记忆)
    ├── .env           # API Keys ← 唯一需要编辑的文件
    ├── config.yaml    # 配置
    ├── sessions/      # 对话历史
    ├── skills/        # 技能
    └── ...
```

## 技术细节

- **Python 运行时**：通过 `uv` 下载独立的 CPython 3.12，不依赖系统 Python
- **依赖管理**：`uv` 创建 venv + 安装所有 hermes-agent 依赖
- **数据隔离**：启动脚本设置 `HERMES_HOME=data/`，所有数据存U盘
- **跨平台启动器**：
  - `.command` = macOS Finder 可双击的 shell 脚本
  - `.bat` = Windows CMD 启动器（通过 WSL 运行）
  - `.sh` = Linux 终端启动器

## Web 管理界面

Hermes Portable 支持可选的 Web 管理界面（[hermes-web-ui](https://github.com/EKKOLearnAI/hermes-web-ui)）。

### 安装

```bash
# 进入便携包目录
cd /path/to/HermesPortable

# 使用内置 Python 安装
./venv/bin/pip install hermes-web-ui
```

### 启用

启动 Hermes 后，在配置面板的「偏好设置」中启用「启动时自动打开 Web UI 管理界面」。

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

- **GitHub 仓库**：https://github.com/yuluyangguang1/hermes-portable
- **上游项目**：https://github.com/NousResearch/hermes-agent
- **Web UI**：https://github.com/EKKOLearnAI/hermes-web-ui

---

*最后更新: 2026-05-06*
