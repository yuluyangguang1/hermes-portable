╔══════════════════════════════════════════╗
║         HERMES  PORTABLE  v0.11.0           ║
║       插上U盘，打开即用的 AI Agent       ║
╚══════════════════════════════════════════╝

【支持平台】
  macOS 10.15+ (Catalina)  →  Hermes.command  双击即用
  Linux (glibc 2.17+)      →  ./Hermes.sh     终端运行
  Windows 10/11            →  Hermes.bat       双击即用（原生支持，Early Beta）

【首次使用】
  双击启动即可，首次会自动打开配置面板：
     macOS    →  Hermes.command  (双击即可)
     Linux    →  ./Hermes.sh
     Windows  →  Hermes.bat  (双击即可)

  在配置面板中填入 API Key，点击「启动」即可使用。

【目录说明】
  data/             所有用户数据（配置/会话/技能）
  data/.env         API 密钥
  data/config.yaml  配置文件
  venv/             Python 依赖（勿动）
  python/           Python 运行时（勿动）
  hermes-agent/     Hermes 源码（勿动）
  config_server.py  Web 配置面板
  chat_viewer.py    聊天记录查看器
  guide.html        操作说明（浏览器打开）
  HermesPortable使用说明.html  中文使用说明

【Windows 备选】
  如果 Hermes.bat 原生运行遇到问题，可使用 Hermes-WSL.bat 通过 WSL2 运行。

【更新 Hermes】
  cd hermes-agent && git pull && cd ..
  venv/bin/pip install -e hermes-agent[all]

【备份】
  只需备份 data/ 目录即可。

【大小】
  当前约 210 MB，U 盘建议 1 GB 以上。
