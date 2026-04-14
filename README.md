# 🚀 Hermes Portable

**U盘即插即用的 AI Agent** — 把 Hermes 和完整的运行环境打包在U盘上，插入任何电脑即可使用。

## 特性

- ✅ **零安装** — 不在宿主机留下任何痕迹
- ✅ **跨平台** — 支持 Windows / macOS / Linux
- ✅ **自包含** — Python 运行时 + 所有依赖打包在U盘内
- ✅ **数据隔离** — 配置、会话、技能全部存储在U盘上
- ✅ **即插即用** — 双击启动脚本即可运行

## 目录结构

```
HermesPortable/
├── start.bat          # Windows 启动器
├── start.sh           # macOS/Linux 启动器
├── setup.bat          # Windows 首次安装
├── setup.sh           # macOS/Linux 首次安装
├── portable/          # 便携环境根目录
│   ├── python/        # 独立 Python 运行时
│   ├── venv/          # 虚拟环境 (所有依赖)
│   └── hermes-agent/  # Hermes 源代码
├── data/              # 用户数据 (配置/会话/技能)
│   ├── config.yaml
│   ├── .env
│   ├── sessions/
│   ├── skills/
│   └── logs/
└── README.md
```

## 快速开始

### 1. 首次安装（只需一次）

**Windows:**
```cmd
setup.bat
```

**macOS/Linux:**
```bash
chmod +x setup.sh && ./setup.sh
```

### 2. 日常使用

**Windows:** 双击 `start.bat`

**macOS/Linux:** `./start.sh`

### 3. 配置 API Key

首次运行后，编辑 `data/.env` 文件，填入你的 API Key：

```
OPENROUTER_API_KEY=your_key_here
# 或者其他 provider 的 key
```

## 支持的 Provider

- OpenRouter、Anthropic、OpenAI
- DeepSeek、Google Gemini、xAI Grok
- Nous Portal、小米 MiMo
- 以及 20+ 其他提供商

## 系统要求

- **U盘**: 至少 2GB 可用空间
- **操作系统**: Windows 10+、macOS 12+、Linux (glibc 2.17+)
- **网络**: 需要互联网连接（调用 LLM API）

## 手动更新

如需更新 Hermes 版本：

```bash
cd portable/hermes-agent
git pull
source ../venv/bin/activate  # 或 Windows 上 activate.bat
pip install -e ".[all]"
```

## 注意事项

- 数据全部存储在 `data/` 目录下，备份此目录即可备份所有数据
- 不建议在多个电脑同时使用同一个U盘实例（可能造成会话冲突）
- 首次安装需要下载 Python 和依赖包，约需 5-10 分钟
