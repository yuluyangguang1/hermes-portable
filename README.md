# 🚀 Hermes Portable

**构建一次，到处使用** — 一个完全自包含的 AI Agent，插上U盘直接运行。

> 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent)（Nous Research）打造的便携版本。

## 支持平台

| 平台 | 启动器 | 要求 |
|------|--------|------|
| **macOS** | `Hermes.command` 双击 | macOS 10.15+ |
| **Linux** | `./Hermes.sh` 终端运行 | glibc 2.17+ |
| **Windows** | `Hermes.bat` 双击 | **需要 WSL2** |

> ⚠️ **Windows 用户**：Hermes Agent 官方不支持原生 Windows，必须通过 WSL2 运行。
> 安装方法：以管理员身份打开 PowerShell → 运行 `wsl --install` → 重启电脑。
> 详见 [微软官方指南](https://learn.microsoft.com/windows/wsl/install)。

## 构建

### macOS / Linux（在 Mac 或 Linux 上构建）

```bash
python3 build.py                    # 输出到 dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # 直接输出到U盘
```

### Windows（在 WSL2 中构建）

```bash
# 1. 克隆或下载本项目
git clone https://github.com/yuluyangguang1/hermes-portable.git
cd hermes-portable

# 2. 运行构建脚本（在 WSL2 终端中）
python3 build.py

# 输出到 dist/HermesPortable/
# 在 Windows 资源管理器中双击 Hermes.bat 即可启动
```

**构建环境要求：** Python 3.8+、git、curl

**构建产物：** ~500MB 的完全自包含文件夹

## 使用（拿到U盘后直接用）

1. 插上U盘
2. 双击启动：
   - **macOS** → `Hermes.command`
   - **Windows** → `Hermes.bat`（需已安装 WSL2）
   - **Linux** → `./Hermes.sh`
3. 首次使用会自动打开配置面板，填入 API Key 即可

**零安装，零依赖，不碰宿主机系统。**

## 目录结构

```
HermesPortable/
├── Hermes.command     # macOS 启动器 (双击)
├── Hermes.bat         # Windows 启动器 (双击，通过 WSL2 运行)
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
├── node/              # Node.js + hermes-web-ui
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
  - `.bat` = Windows 启动器（通过 WSL2 运行，与官方推荐一致）
  - `.sh` = Linux 终端启动器

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

**首次构建需联网：** 构建脚本会自动下载 Node.js v23 并安装 hermes-web-ui，无需手动操作。

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

*最后更新: 2026-05-06*
