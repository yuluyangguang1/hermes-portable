# Hermes Portable

便携版 Hermes Agent — 零安装、单目录、U盘即走

## ✨ 特性

- 🚀 **零安装** — 解压即用，无需安装
- 📁 **单目录** — 所有文件在一个目录
- 💾 **U盘即走** — 拷贝到 U盘，插上就能用
- 🔒 **数据隔离** — 所有数据存储在 data/ 目录
- 🌐 **跨平台** — 支持 macOS 和 Windows
- 🎨 **配置中心** — Web 界面配置，简单易用

## 📦 下载

从 [GitHub Releases](https://github.com/yuluyangguang1/hermes-portable/releases) 下载最新版本。

### macOS
```bash
# 下载 Universal 版本
HermesPortable-Universal.zip

# 解压后双击 Hermes.command 启动
```

### Windows
```bash
# 下载 Windows 版本
HermesPortable-Windows-x64.zip

# 解压后双击 Hermes.bat 启动
```

## 🚀 快速开始

### 1. 下载并解压

```bash
# macOS
unzip HermesPortable-Universal.zip
cd HermesPortable

# Windows
# 解压 HermesPortable-Windows-x64.zip
```

### 2. 启动

```bash
# macOS
./Hermes.command

# Windows
Hermes.bat
```

### 3. 配置

启动后会自动打开配置中心：
- 访问 http://127.0.0.1:17520
- 选择 LLM 提供商
- 输入 API Key
- 选择模型
- 点击保存

### 4. 启动 Hermes

配置完成后，点击"启动"按钮。

## 📁 目录结构

```
HermesPortable/
├── Hermes.command          # macOS 启动器
├── Hermes.bat              # Windows 启动器
├── lib/
│   ├── config_server.py    # 配置服务器
│   ├── config/
│   │   ├── index.html      # 配置中心前端
│   │   └── index-standalone.html  # 自包含版
│   └── fix_shims.py        # 修复脚本
├── tools/
│   └── build.py            # 构建脚本
├── data/
│   ├── .env                # API Keys
│   ├── config.yaml         # 模型配置
│   └── runtime.json        # 运行时信息
├── venv-macos-arm64/       # macOS ARM64 虚拟环境
├── venv-macos-x64/         # macOS x64 虚拟环境
├── venv-windows-x64/       # Windows x64 虚拟环境
├── python-macos-arm64/     # macOS ARM64 Python
├── python-macos-x64/       # macOS x64 Python
├── python-windows-x64/     # Windows x64 Python
├── node-macos-arm64/       # macOS ARM64 Node.js
├── node-macos-x64/         # macOS x64 Node.js
├── node-windows-x64/       # Windows x64 Node.js
├── hermes-agent/           # Hermes Agent 源码
├── uv                      # uv 包管理器
├── VERSION                 # 版本号
└── README.md               # 本文件
```

## 🔧 配置中心

配置中心提供 Web 界面管理 Hermes 配置：

### 功能
- ✅ LLM 提供商管理
- ✅ API Key 管理
- ✅ 模型选择
- ✅ 渠道配置
- ✅ 偏好设置
- ✅ 版本更新
- ✅ 配置导入/导出

### 支持的 LLM 提供商
- OpenRouter
- Anthropic (Claude)
- OpenAI (GPT)
- DeepSeek
- Google (Gemini)
- xAI (Grok)
- Mistral
- 智谱 (GLM)
- 通义千问 (Qwen)
- Kimi
- MiniMax
- 小米 (MiMo)
- 豆包 (Doubao)
- 等 74+ 个提供商

### 支持的渠道
- Telegram
- Discord
- Slack
- WhatsApp
- WeChat
- Email
- Signal
- Matrix

## 🛠️ 开发

### 构建

```bash
# 构建 Universal 版本
python3 tools/build.py

# 构建特定平台
python3 tools/build.py --platform macos-arm64
python3 tools/build.py --platform macos-x64
python3 tools/build.py --platform windows-x64
```

### 测试

```bash
# 测试配置服务器
python3 lib/config_server.py

# 测试 Hermes Agent
./venv-macos-arm64/bin/hermes --version
```

## 📝 更新日志

### v0.23.0 (2026-07-21)
- 配置中心全面优化
- 渠道配置更新
- 前端设计优化
- 无障碍支持
- 动画优化

### v0.22.0 (2026-07-20)
- Token 生成 + runtime.json
- Preflight 自检
- kill_tree 子进程清理
- 浏览器带 Token 打开

### v0.21.5 (2026-07-17)
- PYTHONHOME 修复
- hermes-web-ui 安装
- 全面优化

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
