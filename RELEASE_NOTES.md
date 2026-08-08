# Hermes Portable v1.20.15 发版说明

## 🎯 本期重点

### 配置中心新增「桌面版」启动按钮
- ✅ 配置中心（:17520）顶栏新增「桌面版」按钮
- ✅ 后端 `/api/desktop/status`（探测包内是否含桌面版运行时）
- ✅ 后端 `/api/desktop/start`（启动，返回 launched / missing / wrong-arch / error）
- ✅ **点击即有提示**：未打包 → "此便携包未包含桌面版运行时"；架构不匹配 → "请安装 Rosetta 2 或下载对应架构包"；启动成功 → "桌面版已启动"
- ✅ `desktop_start()` 增加**架构检查**：arm64 App 在 x86_64 主机返回 `wrong-arch`，避免 `open` 命令"假成功"（命令立即返回但 App 实际打不开）

### 默认启动模式改回终端 CLI
- ✅ `Hermes.command` 的 `LAUNCH_MODE` 由 `desktop` 改回 `cli`
- 原因：桌面版 App 需单独 electron 构建、且为单一架构，双击不应默认去找不存在/架构不符的 App。桌面版改为可选（配置中心按钮或 `--desktop` 参数显式启用）

### 配套修复（v1.20.9 ~ v1.20.14 累积）
- ✅ **Web UI 真正启动**：修复 `node/package.json` 缺失（type:module）与 server 路径（`node/dist` 软链），Web UI（:8648）从静默失败变 HTTP 200
- ✅ **配置中心常驻**：`start_config_server` 加 `setsid` 脱离进程组，退出终端 / 退出 Hermes 后配置中心仍在
- ✅ **Web UI 强制包内 Node.js**：显式用 `$NODE_DIR/bin/node` 启动，不再静默回退系统 Node（实测所有 webui 进程 node 路径均为包内 v24）
- ✅ **Node.js 升回 24 LTS**：macOS / Linux 用 Node 24（满足 24+ 预期）；Windows 因 CI runner 崩溃暂用 22
- ✅ **Hermes 网关可启动**：修复 editable finder `_BASE` 路径计算（×4 落到 `venv/` 而非包根，导致 `hermes_cli` 找不到）

## 📦 文件结构
（同 v1.20.0，运行时目录为 `venv/` `python/` `node/` `runtime/` 扁平结构）

---

# Hermes Portable v1.20.0 发版说明

## 🎉 主要更新

### 配置中心修复与增强
- ✅ 修复 standalone 版本模型列表坏格式（61 个 provider 引号混用导致 JS 解析断裂）
- ✅ 删除后端配置服务器中失效的在线 catalog 模板占位符（no-op 死代码）
- ✅ 修复保存配置时 default 模型字段前缀丢失（nous / xiaomi-token-plan 等路由错误）
- ✅ 配置中心图标库补全为 72 个真实品牌 SVG（原仅 32 个，50 个 provider 无图标）
- ✅ 保存 / 启动按钮反馈改为瞬时闪光态（flash-ok / flash-err），既明显又不卡操作
- ✅ 同厂商多入口加区分标签（中转 / 代码 / 北京 / 海外 / TokenHub 等），选择区更清晰
- ✅ 修复首次运行引导每次刷新都弹出的问题（改为按真实配置判断首次运行状态）
- ✅ 修复模型预览重复前缀（如 `xiaomi/xiaomi/mimo-v2.5-pro` → `xiaomi/mimo-v2.5-pro`）
- ✅ 查看 .env 改为页内弹窗，不再依赖浏览器弹窗权限
- ✅ 修复测试连接功能：修正 Xiaomi 错误域名，覆盖全部 74 个 provider（原仅 18 个可测）
- ✅ 移除 DeepSeek 已退役别名 `deepseek-chat` / `deepseek-reasoner`（2026-07-24 retired）

### 配置同步上游
- 同步 Hermes Agent 上游新增可配置能力（provider 插件、config schema 开关），详见本期审查

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
- 真实品牌图标（icons/ 72 个 SVG）
- 设计 Token 系统 + 统一排版
- 移动端响应式
- 首次运行引导按真实配置判断，不再每次刷新弹出

### 启动流程
- PYTHONHOME 检测优化
- fix_shims.py 修复
- Watchdog 自动重启
- Token 认证支持

---

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

### 配置中心模型列表修复
- ✅ 修复 61 个模型数组单双引号混用问题（JS 解析断裂导致模型列表渲染不完整）
- ✅ 统一所有模型数组使用单引号，消除 `\"` 混入导致的语法错误

### macOS 启动权限增强
- ✅ 扩展自修复逻辑覆盖 npm/npx/corepack CLI 脚本
- ✅ 新增 node/.bin/ 目录可执行权限修复
- ✅ 新增 hermes-agent Python 脚本权限修复
- ✅ 新增首次启动日志（data/.first-launch.log）便于排查权限问题

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
- 修复模型数组引号混用（61 个 Provider）

### 启动流程
- PYTHONHOME 检测优化
- fix_shims.py 修复
- Watchdog 自动重启
- Token 认证支持
- macOS quarantine 属性清理
- 增强自修复：npm/npx/corepack、hermes-agent、node/.bin/
- 首次启动日志记录

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

### v0.24.2 (2026-07-31)
- 修复配置中心 61 个模型数组单双引号混用问题（JS 解析断裂，模型列表渲染不完整）
- 增强 macOS 自修复逻辑：npm/npx/coreport、node/.bin/、hermes-agent Python 脚本
- 新增首次启动日志（data/.first-launch.log）便于排查权限问题

### v0.24.0 (2026-07-27)
- 新增快速切换模型功能（参考 OpenClaw，配置中心内一键切换）
- 修复启动脚本 4 类严重 Bug（缩进/未定义函数/作用域/文件不存在）
- 修复 open_url() 函数作用域（不再定义在 if 块内）
- 修复 watchdog 子 shell 变量隔离（改用 PID 文件通信，重启后正确更新）
- 优化 PYTHONHOME 检测（支持任意 python3.x，不再硬编码 3.12）
- 修复 macOS `open` 非阻塞问题（desktop mode增加等待）
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
