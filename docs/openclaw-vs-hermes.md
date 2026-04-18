# OpenClaw 与 Hermes Portable — 两条路线，两种思路

> 本文基于公开信息整理，仅呈现差异，不作优劣判断。  
> 最后更新：2026 年 4 月

---

## 一、一句话定位

| | 定位 |
|---|------|
| **OpenClaw** | "你自己的个人 AI 助手——任何系统、任何平台，龙虾方式。🦞" |
| **Hermes Portable** | "U 盘即机器——插入任意电脑，打开即用，拔走即无痕。" |

两者都叫「个人 AI 助手」，但打开方式截然不同。

---

## 二、基本信息速览

| 维度 | OpenClaw | Hermes Portable |
|------|----------|-----------------|
| 首次发布 | 2025-11 | 2026-03 |
| GitHub Stars | 359,899 | 98,747 (hermes-agent 上游) |
| 主语言 | TypeScript | Python |
| 协议 | MIT | MIT |
| 赞助商 | OpenAI · GitHub · NVIDIA · Vercel 等 | 社区驱动 |

---

## 三、架构与运行方式

### OpenClaw

```
用户设备 (Mac/Linux/Windows+WSL)
  └─ Gateway (Node.js 守护进程, 常驻后台)
       ├─ 多渠道连接器 (WhatsApp / Telegram / Signal / WeChat … 20+)
       ├─ Agent 引擎 (对话 + 工具调用)
       ├─ Skills 注册表 (ClawHub)
       ├─ MCP 桥接 (mcporter)
       └─ 可选伴侣 App (macOS 菜单栏 / iOS / Android 节点)
```

- **运行依赖**：Node 24（或 22.16+）+ npm/pnpm/bun
- **安装方式**：`npm install -g openclaw@latest` → `openclaw onboard --install-daemon`
- **守护进程**：launchd / systemd user service，开机自启
- **数据位置**：本机磁盘（`~/.openclaw/`）
- **沙箱**：Docker 容器隔离非主会话

### Hermes Portable

```
U 盘 (USB)
  └─ HermesPortable/
       ├─ PortablePython/ (嵌入式 Python + venv)
       ├─ hermes-agent (上游 agent)
       ├─ config_server.py (Web 配置面板)
       ├── tools/ (自动下载的工具二进制)
       └── data/ (配置 + 日志 + 技能 + 记忆)
```

- **运行依赖**：零——Python 解释器与所有 pip 包随 U 盘携带
- **安装方式**：运行 `build.py` / `Hermes.bat`（首次自动创建 venv + 安装依赖）
- **守护进程**：无常驻服务，按需启动
- **数据位置**：全部在 U 盘内，拔盘即走
- **沙箱**：无 Docker，依托本机终端权限

---

## 四、核心差异对比

### 1. 部署哲学

| | OpenClaw | Hermes Portable |
|---|----------|-----------------|
| 归属感 | 装在"我的电脑"上 | 装在"我的 U 盘"上 |
| 设备绑定 | 需要固定设备运行 Gateway | 任意电脑插入即用 |
| 系统侵入性 | 修改系统服务 (launchd/systemd) | 不修改宿主系统任何文件 |
| 离线能力 | 需网络调用 LLM API | 同样需要网络调用 API |

### 2. 多渠道通讯

OpenClaw 内建 **20+ 消息渠道连接器**——WhatsApp、Telegram、Signal、Discord、Slack、iMessage、WeChat、QQ、LINE、Matrix 等——统一汇聚到 Gateway。

Hermes Portable 的通讯层通过 **hermes-agent** 的 Channel 系统实现，当前支持 Telegram、WhatsApp、Discord、Slack 等主流平台，渠道数量略少于 OpenClaw。

### 3. 工具与技能

| | OpenClaw | Hermes Portable |
|---|----------|-----------------|
| 技能市场 | ClawHub（社区技能注册表） | 内建 60+ 技能 + skill_manage 动态创建 |
| MCP 支持 | mcporter 桥接 | 原生 MCP 客户端 + mcporter |
| 浏览器自动化 | 内建 browser 工具 | 内建 browser 工具 |
| 终端执行 | bash / process 工具 | terminal 工具 |
| 代码执行 | Agent 内直接调用 | execute_code (Python sandbox) |

### 4. 伴侣应用

OpenClaw 提供 **macOS 菜单栏 App**、**iOS/Android 节点**，支持语音唤醒（Voice Wake）和实时 Canvas 可视化画布。

Hermes Portable 目前以 **Web 配置面板**（`127.0.0.1:17520`）作为图形界面，支持 API Key 管理、渠道配置、模型切换、自动更新，暂无原生桌面/移动端 App。

### 5. 安全模型

| | OpenClaw | Hermes Portable |
|---|----------|-----------------|
| DM 策略 | 配对码验证 (pairing code) + allowlist | 依赖上游 hermes-agent 的权限体系 |
| 沙箱 | Docker 隔离非主会话 | 无容器隔离 |
| 数据驻留 | 本机磁盘 | U 盘（物理可控） |
| 无痕程度 | 卸载后可能残留系统服务/配置 | 拔掉 U 盘，宿主机无残留 |

### 6. 平台覆盖

| 平台 | OpenClaw | Hermes Portable |
|------|----------|-----------------|
| macOS | ✅ 原生 | ✅ |
| Linux | ✅ | ✅ |
| Windows | ⚠️ 需要 WSL2 | ✅ 原生支持 (Hermes.bat) |
| 移动端 | iOS / Android 节点 | 暂无 |

---

## 五、使用场景画像

### OpenClaw 更适合的人群

- 有自己的固定电脑，希望 AI 助手**常驻后台**、随时响应
- 需要同时在 WhatsApp、Telegram、Discord 等**多平台收发消息**
- 看重 **macOS 菜单栏 + 语音唤醒 + 移动端伴侣** 的一体化体验
- 团队/群聊场景，需要 Docker 沙箱隔离不同会话

### Hermes Portable 更适合的人群

- 经常在**不同电脑之间切换**（公司、家里、图书馆、出差）
- 对**隐私极度敏感**，不希望在任何宿主机器上留下痕迹
- 受限环境（公司电脑无法安装软件、没有管理员权限）
- Windows 用户希望**零 WSL 依赖**直接运行
- 喜欢"**插上即用、拔走即无**"的工作方式

---

## 六、技术栈对照表

| 层面 | OpenClaw | Hermes Portable |
|------|----------|-----------------|
| 运行时 | Node.js 24 | 嵌入式 Python 3.12+ |
| 包管理 | npm / pnpm / bun | pip + venv (自包含) |
| 配置方式 | CLI (`openclaw onboard`) | Web 面板 (`config_server.py`) |
| 前端 | 命令行优先 + Web surface | 浏览器 UI (深青主题) |
| 日志 | Gateway 内建 | data/logs/ 目录 |
| 更新 | `npm update -g openclaw` | 内建自动更新 (update.py) |
| 文档 | docs.openclaw.ai (详尽) | guide.html (简洁) |

---

## 七、社区与生态

| | OpenClaw | Hermes Portable |
|---|----------|-----------------|
| 赞助商 | OpenAI / GitHub / NVIDIA / Vercel / Blacksmith / Convex | 无 |
| 技能生态 | ClawHub (社区注册表) | 上游 hermes-agent 技能库 (60+) |
| Discord 社区 | 有 (discord.gg/clawd) | 无独立社区 |
| 贡献者 | 活跃开源社区 | 个人项目 |

---

## 八、总结：两条路线，各有场景

OpenClaw 走的是 **"装机即服务"** 路线——在你的主力电脑上部署一个常驻的 AI Gateway，像安装一个本地版的 Slack/Discord 那样，打通所有通讯渠道，配以伴侣 App 和语音交互，追求的是 **"无处不在的在线感"**。

Hermes Portable 走的是 **"U 盘即身份"** 路线——把完整的 AI 环境压缩到一个 USB 设备中，不依赖任何一台特定电脑，不留任何系统级痕迹，追求的是 **"随时随地的自由度"**。

两者并非对立关系。在一台固定的工作站上运行 OpenClaw Gateway，在 U 盘里放一份 Hermes Portable 作为"出差版"——这种组合在实践中完全可行。

选择哪条路线，取决于你更在意"常驻在线"还是"自由移动"。

---

*本文数据来源：OpenClaw GitHub 仓库 (openclaw/openclaw)、Hermes Portable GitHub 仓库 (yuluyangguang1/hermes-portable)、hermes-agent GitHub 仓库 (NousResearch/hermes-agent)，截至 2026 年 4 月 14 日。*
