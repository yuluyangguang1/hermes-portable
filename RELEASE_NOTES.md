# Hermes Portable v0.24.1 发版说明

## 🎉 主要更新

### 构建系统修复
- ✅ 修复 hermes-agent setup.py 阻止 wheel/sdist 安装问题（改用可编辑安装）
- ✅ 修复 Python 二进制文件缺少执行权限问题
- ✅ 修复 macOS Gatekeeper 阻止未签名二进制文件运行问题
- ✅ 修复 create-release 作业中的制品结构不匹配问题
- ✅ 确保每次构建时安装最新版本的 hermes-web-ui

### 配置文件修复
- ✅ 修复 lib/config/index.html 在便携式构建中缺失问题
- ✅ 修复 lib/config/index-standalone.html 在便携式构建中缺失问题

## 📦 文件结构

```
HermesPortable-Universal.zip
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
└── VERSION                 # 版本号
```

## 🔧 技术改进

### 配置中心
- 使用 Tabler Icons CDN
- 添加设计 Token 系统
- 统一排版规范
- 优化移动端响应式

### 启动流程
- PYTHONHOME 检测优化
- fix_shims.py 修复
- Watchdog 自动重启
- Token 认证支持
- macOS quarantine 属性清理

### 渠道支持
- Telegram
- Discord
- Slack
- WhatsApp
- WeChat
- Email
- Signal
- Matrix

## 📝 使用方法

### macOS
```bash
# 双击 Hermes.command 启动
# 或终端运行
./Hermes.command
```

### Windows
```bash
# 双击 Hermes.bat 启动
# 或命令行运行
Hermes.bat
```

### 配置中心
```
http://127.0.0.1:17520
```

## 🔗 相关链接

- [GitHub 仓库](https://github.com/yuluyangguang1/hermes-portable)
- [问题反馈](https://github.com/yuluyangguang1/hermes-portable/issues)
- [Hermes Agent 官方](https://hermes-agent.nousresearch.com/)

## 📋 更新日志

### v0.24.1 (2026-07-31)
- 修复 hermes-agent setup.py 阻止 wheel/sdist 安装问题（改用可编辑安装 + 路径后处理）
- 修复 Python 二进制文件缺少执行权限问题
- 修复 macOS Gatekeeper 阻止未签名二进制文件运行问题（xattr 清理）
- 修复 lib/config/index.html 在便携式构建中缺失问题
- 修复 create-release 作业中的制品结构不匹配问题
- 确保每次构建时安装最新版本的 hermes-web-ui (--force 标志)

### v0.24.0 (2026-07-27)
- 新增快速切换模型功能（参考 OpenClaw，配置中心内一键切换）
- 修复启动脚本 4 类严重 Bug（缩进/未定义函数/作用域/文件不存在）
- 修复 open_url() 函数作用域（不再定义在 if 块内）
- 修复 watchdog 子 shell 变量隔离（改用 PID 文件通信，重启后正确更新）
- 优化 PYTHONHOME 检测（支持任意 python3.x，不再硬编码 3.12）
- 修复 macOS `open` 非阻塞问题（desktop mode 增加等待）
- 新增远程构建工作流（build.yml，支持 workflow_dispatch 填 tag 或 push v* tag 触发三平台构建 + GitHub Release）

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
