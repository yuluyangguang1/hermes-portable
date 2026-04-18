# 🚀 Hermes Portable

**构建一次，到处使用** — 一个完全自包含的 AI Agent，插上U盘直接运行。

## 支持平台

| 平台 | 启动器 | 要求 |
|------|--------|------|
| **macOS** | `Hermes.command` 双击 | macOS 10.15+ |
| **Linux** | `./Hermes.sh` 终端运行 | glibc 2.17+ |
| **Windows** | `Hermes.bat` 双击 | **原生支持，无需 WSL** ✅ |

## 构建

### macOS / Linux（在 Mac 或 Linux 上构建）

```bash
python3 build.py                    # 输出到 dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # 直接输出到U盘
```

### Windows（在 Windows 上构建）

```powershell
# 1. 克隆或下载本项目
git clone https://github.com/your-repo/HermesPortable.git
cd HermesPortable

# 2. 运行 Windows 专用构建脚本
python build_windows.py

# 输出到 dist/HermesPortable/
# 双击 Hermes.bat 即可启动
```

**构建环境要求：** Python 3.8+、git、curl

**构建产物：** ~500MB 的完全自包含文件夹

## 使用（拿到U盘后直接用）

1. 插上U盘
2. 双击启动：
   - **macOS** → `Hermes.command`
   - **Windows** → `Hermes.bat`（无需 WSL！）
   - **Linux** → `./Hermes.sh`
3. 首次使用会自动打开配置面板，填入 API Key 即可

**零安装，零依赖，不碰宿主机系统。**

## 目录结构

```
HermesPortable/
├── Hermes.command     # macOS 启动器 (双击)
├── Hermes.bat         # Windows 启动器 (双击) ← 原生支持
├── Hermes.sh          # Linux 启动器
├── Hermes-Config.bat  # Windows 配置面板专用入口
├── README.txt         # 用户指南
├── python/            # Python 独立运行时（平台特定）
├── venv/              # 虚拟环境 + 所有依赖（平台特定）
├── hermes-agent/      # Hermes 源代码
├── config_server.py   # Web 配置面板
├── update.py          # 自动更新模块
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
  - `.bat` = Windows CMD 原生启动器（**无需 WSL**）
  - `.sh` = Linux 终端启动器

## 备份与更新

- **备份**：只复制 `data/` 目录
- **更新 Hermes**：
  - 双击 `Hermes-Config.bat`（Windows）或启动配置面板
  - 点击「检查更新」按钮
