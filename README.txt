╔══════════════════════════════════════════╗
║         HERMES  PORTABLE  v0.9           ║
║       插上U盘，打开即用的 AI Agent       ║
╚══════════════════════════════════════════╝

【支持平台】
  macOS 10.15+ (Catalina)  →  Hermes.command  双击即用
  Linux (glibc 2.17+)      →  ./Hermes.sh     终端运行
  Windows 10/11            →  Hermes.bat       需要 WSL

【首次使用】
  1. 打开 data/.env 文件
  2. 填入你的 API Key（去掉前面的 #）
  3. 双击启动：
     macOS    →  Hermes.command  (双击即可)
     Linux    →  ./Hermes.sh
     Windows  →  Hermes.bat  (需先装 WSL: wsl --install)

  首次启动会自动打开 Web 配置面板，方便配置。

【Windows 用户注意】
  Hermes 不支持 Windows 原生运行，必须通过 WSL。
  安装 WSL 步骤：
    1. 以管理员身份打开 PowerShell
    2. 运行: wsl --install
    3. 重启电脑
    4. 详情: https://learn.microsoft.com/wsl/install

【Linux 用户注意】
  当前 U 盘仅包含 macOS 版 Python。首次在 Linux 上使用：
    1. 插入 U 盘
    2. cd /path/to/HermesPortable
    3. ./linux-rebuild.sh
  这会自动重建 Linux 兼容的 Python 和依赖。

【目录说明】
  data/             所有用户数据（配置/会话/技能）
  data/.env         API 密钥
  data/config.yaml  配置文件
  venv/             Python 依赖（勿动）
  python/           Python 运行时（勿动）
  hermes-agent/     Hermes 源码（勿动）
  build.py          完整构建脚本
  linux-rebuild.sh  Linux 快速重建脚本
  config_server.py  Web 配置面板
  chat_viewer.py    聊天记录查看器

【更新 Hermes】
  cd hermes-agent && git pull && cd ..
  venv/bin/pip install -e hermes-agent[all]

【备份】
  只需备份 data/ 目录即可。

【大小】
  当前约 210 MB，U 盘建议 1 GB 以上。
