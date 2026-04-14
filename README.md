# 🚀 Hermes Portable

**构建一次，到处使用** — 一个完全自包含的 AI Agent，插上U盘直接运行。

## 概念

```
 开发者/构建机                        用户U盘
┌──────────────┐    build.py     ┌─────────────────────┐
│  Python 3.12  │  ──────────►   │  HermesPortable/    │
│  git          │                │  ├── Hermes.bat     │  ← 双击启动
│  curl         │                │  ├── Hermes.command │  ← macOS 双击
│               │                │  ├── Hermes.sh      │  ← Linux 终端
└──────────────┘                │  ├── python/        │  ← 独立 Python
                                │  ├── venv/          │  ← 全部依赖
                                │  ├── hermes-agent/  │  ← 源码
                                │  └── data/          │  ← 用户数据
                                └─────────────────────┘
                                      ↑ 复制到U盘即可
```

## 构建（在你自己的机器上执行一次）

```bash
python3 build.py                    # 输出到 dist/HermesPortable/
python3 build.py /Volumes/MyUSB     # 直接输出到U盘
```

**构建环境要求：** macOS/Linux，有 `python3`、`git`、`curl`

**构建产物：** ~500MB 的完全自包含文件夹

## 使用（拿到U盘后直接用）

1. 插上U盘
2. 编辑 `data/.env` 填入 API Key（首次）
3. 双击启动：
   - **macOS** → `Hermes.command`
   - **Windows** → `Hermes.bat`
   - **Linux** → `./Hermes.sh`

**零安装，零依赖，不碰宿主机系统。**

## 目录结构

```
HermesPortable/
├── Hermes.command     # macOS 启动器 (双击)
├── Hermes.bat         # Windows 启动器 (双击)
├── Hermes.sh          # Linux 启动器
├── README.txt         # 用户指南
├── python/            # Python 3.12 独立运行时
├── venv/              # 虚拟环境 + 所有依赖
├── hermes-agent/      # Hermes 源代码
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
  - `.bat` = Windows CMD 启动器
  - `.sh` = Linux 终端启动器

## 备份与更新

- **备份**：只复制 `data/` 目录
- **更新 Hermes**：
  ```bash
  cd hermes-agent && git pull
  venv/bin/pip install -e .[all]
  ```
