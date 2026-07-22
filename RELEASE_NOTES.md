# Hermes Portable v0.23.0 发版说明

## 🎉 主要更新

### 配置中心全面优化
- ✅ 使用 Tabler Icons 替换 Unicode 表情符号
- ✅ 添加设计 Token（间距/圆角/阴影/动画）
- ✅ 统一排版（行高/字间距/圆角）
- ✅ 修复 footer 边框问题
- ✅ 修复设置区域间距

### 渠道配置更新
- ✅ 添加 Discord Application ID 字段
- ✅ 更新 8 个渠道配置（Telegram/Discord/Slack/WhatsApp/WeChat/Email/Signal/Matrix）

### 前端设计优化
- ✅ 图片懒加载
- ✅ 字体优化（font-display: swap）
- ✅ 响应式设计统一
- ✅ 颜色对比度优化
- ✅ 字体大小优化（12px → 14px）
- ✅ 阴影层次优化
- ✅ 间距系统优化

### 无障碍支持
- ✅ 添加 prefers-reduced-motion
- ✅ 添加 focus-visible 焦点指示器
- ✅ 添加 ARIA 标签
- ✅ 添加表单标签

### 动画优化
- ✅ 修复 transition: all
- ✅ 添加 ease-out 缓动
- ✅ 统一动画时长

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
