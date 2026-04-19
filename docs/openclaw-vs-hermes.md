# OpenClaw 与 Hermes — 两种个人 AI 助手的路线选择

> 本文基于公开信息整理，仅呈现差异，不作优劣判断。  
> 数据截至：2026 年 4 月 14 日

---

## 一、项目画像

| | OpenClaw 🦞 | Hermes ☤ |
|---|------------|----------|
| Slogan | "Your own personal AI assistant. The lobster way." | "The self-improving AI agent that grows with you." |
| 创始方 | 社区开源 | Nous Research |
| 首次发布 | 2025-11 | 2025-07 |
| GitHub Stars | 359,899 | 98,747 |
| 主语言 | TypeScript | Python |
| 协议 | MIT | MIT |
| 赞助商 | OpenAI · GitHub · NVIDIA · Vercel · Blacksmith · Convex | Nous Research 自有 |
| 设计哲学 | 通讯优先——打通所有消息渠道，让 AI 随时响应 | 学习优先——Agent 从经验中自我进化，积累技能与记忆 |

---

## 二、运行方式

### OpenClaw

```
本地设备 (macOS / Linux / Windows+WSL)
  └─ Gateway (Node.js 守护进程, 常驻后台)
       ├─ 渠道连接器 (20+ 消息平台)
       ├─ Agent 引擎
       ├─ 技能注册表 (ClawHub)
       ├─ MCP 桥接 (mcporter)
       └─ 可选伴侣 App (macOS 菜单栏 / iOS / Android 节点)
```

- **运行时**：Node 24（或 22.16+）+ npm/pnpm/bun
- **安装**：`npm install -g openclaw@latest` → `openclaw onboard --install-daemon`
- **守护方式**：launchd / systemd user service，开机自启
- **数据位置**：本机磁盘 `~/.openclaw/`

### Hermes

```
任意环境 (终端)
  └─ hermes (Python 进程)
       ├─ CLI TUI (多行编辑 / 斜杠命令 / 流式输出)
       ├─ Gateway (Telegram / Discord / Slack / WhatsApp / Signal / Email)
       ├─ 技能系统 (内建 + agentskills.io 标准)
       ├─ MCP 集成 (原生客户端)
       └─ 终端后端 (Local / Docker / SSH / Daytona / Singularity / Modal)
```

- **运行时**：Python 3.11+，通过 uv / pip 安装
- **安装**：`curl -fsSL https://.../install.sh | bash`
- **守护方式**：`hermes gateway start` 按需启动
- **数据位置**：`~/.hermes/`

---

## 三、核心差异

### 1. 渠道覆盖

| 平台 | OpenClaw | Hermes |
|------|----------|--------|
| Telegram | ✅ | ✅ |
| Discord | ✅ | ✅ |
| Slack | ✅ | ✅ |
| WhatsApp | ✅ | ✅ |
| Signal | ✅ | ✅ |
| iMessage / BlueBubbles | ✅ | — |
| WeChat | ✅ | — (社区桥接 HermesClaw) |
| QQ | ✅ | — |
| LINE | ✅ | — |
| Matrix | ✅ | — |
| Microsoft Teams | ✅ | — |
| IRC | ✅ | — |
| Email | — | ✅ |
| macOS / iOS / Android 原生 | ✅ (伴侣 App) | — |
| 终端 TUI | — | ✅ (完整 TUI) |

OpenClaw 在渠道数量上覆盖面更广，尤其在亚洲通讯工具（WeChat、QQ、LINE）方面。

Hermes 在终端交互体验上投入更多，提供完整的 TUI（多行编辑、流式工具输出、中断重定向）。

### 2. 学习与记忆

| 能力 | OpenClaw | Hermes |
|------|----------|--------|
| 跨会话记忆 | 通过记忆插件 | 内建 FTS5 会话搜索 + LLM 摘要 |
| 用户画像 | — | Honcho 辩证建模，持续更新 |
| 技能自创建 | 通过 ClawHub | 内建——复杂任务后自动保存为技能 |
| 技能自进化 | — | 使用中自动修补过时/错误的技能 |
| 知识持久化 | — | 定期 nudge 机制，主动固化经验 |

Hermes 的核心差异化在于 **闭环学习**——Agent 不只是执行任务，还会从经验中提炼技能、改进技能、并持续构建用户画像。

### 3. 运行环境

| 环境 | OpenClaw | Hermes |
|------|----------|--------|
| 本机终端 | ✅ | ✅ |
| Docker | ✅ (沙箱) | ✅ (终端后端) |
| SSH 远程 | ✅ (Remote Gateway) | ✅ (SSH 后端) |
| $5 VPS | 可行 | 可行 |
| GPU 集群 | — | ✅ (Modal / Singularity) |
| Serverless (按需计费) | — | ✅ (Daytona / Modal) |
| Android (Termux) | — | ✅ |
| Windows 原生 (非 WSL) | — | ⚠️ 需 WSL2 |

Hermes 提供 **6 种终端后端**，可以在 Serverless 基础设施上运行——空闲时几乎零成本，按需唤醒。

OpenClaw 的运行模式更偏向"装在固定设备上，长期在线"。

### 4. 安全模型

| 维度 | OpenClaw | Hermes |
|------|----------|--------|
| DM 验证 | 配对码 + allowlist | DM pairing + 命令审批 |
| 沙箱 | Docker 隔离非主会话 | 容器隔离 (可选) |
| 命令审批 | — | 细粒度命令审批系统 |
| 数据驻留 | 本机磁盘 | 本机磁盘 / 远程环境 |

### 5. 工具生态

| 能力 | OpenClaw | Hermes |
|------|----------|--------|
| 内建工具数量 | browser / canvas / nodes / cron / discord 等 | 40+ 工具 (terminal / browser / cron / memory / session 等) |
| 技能市场 | ClawHub (社区注册表) | agentskills.io (开放标准) + 内建 60+ |
| MCP 支持 | mcporter 桥接 | 原生 MCP 客户端 |
| 子 Agent | — | delegate_task (并行子任务) |
| Python 脚本执行 | — | execute_code (RPC 工具调用) |
| 定时任务 | ✅ | ✅ (cron + 多平台投递) |

### 6. 模型支持

| | OpenClaw | Hermes |
|---|----------|--------|
| 切换方式 | 配置文件 / onboard 向导 | `hermes model` 一行切换 |
| OpenAI | ✅ | ✅ |
| Anthropic (Claude) | ✅ | ✅ |
| OpenRouter | ✅ | ✅ (200+ 模型) |
| NVIDIA NIM | — | ✅ (Nemotron) |
| Xiaomi MiMo | — | ✅ |
| Kimi / Moonshot | — | ✅ |
| MiniMax | — | ✅ |
| Hugging Face | — | ✅ |
| 自定义端点 | ✅ | ✅ |

Hermes 在模型供应商覆盖上更为广泛，尤其在亚洲模型（MiMo、Kimi、MiniMax、GLM）方面。

---

## 四、迁移与互通

Hermes 内建了从 OpenClaw 迁移的工具：

```
hermes claw migrate              # 交互式迁移
hermes claw migrate --dry-run    # 预览
hermes claw migrate --preset user-data   # 仅迁移数据，不含密钥
```

可迁移内容：SOUL.md、记忆、技能、命令白名单、消息渠道配置、API Key、TTS 资产、工作区指令。

社区项目 **HermesClaw** 还支持在同一微信账号上同时运行两个 Agent。

---

## 五、技术栈对照

| 层面 | OpenClaw | Hermes |
|------|----------|--------|
| 运行时 | Node.js 24 | Python 3.11+ |
| 包管理 | npm / pnpm / bun | uv / pip |
| 安装体积 | ~数百 MB (含 Node 生态) | ~数百 MB (含 Python 生态) |
| 前端交互 | CLI + Web Surface + 原生 App | TUI (终端) + 消息渠道 |
| 文档 | docs.openclaw.ai (详尽) | hermes-agent.nousresearch.com/docs |
| 社区 | Discord (discord.gg/clawd) | Discord (discord.gg/NousResearch) |
| 迁移工具 | — | `hermes claw migrate` |

---

## 六、使用场景画像

### OpenClaw 更适合的场景

- 日常通讯跨 **10+ 个消息平台**，需要统一的 AI 入口
- macOS 用户，希望 **菜单栏常驻 + 语音唤醒 + 移动端伴侣 App**
- 偏好 **npm 生态** 和 TypeScript 可读性
- 看重 **ClawHub 社区技能市场** 的即时可用性

### Hermes 更适合的场景

- 需要在 **VPS / GPU 集群 / Serverless** 上运行 Agent
- 重视 Agent 的 **自我学习与技能进化** 能力
- 需要 **子 Agent 并行化** 复杂任务
- 已有亚洲模型账号（MiMo / Kimi / MiniMax / GLM），希望直接切换
- 从 OpenClaw 迁移，已有存量配置和技能

---

## 七、一句话总结

OpenClaw 走的是 **"全渠道通讯枢纽"** 路线——把 AI 助手接入你已经在用的所有聊天工具，配上原生 App，追求无处不在的在线感。

Hermes 走的是 **"自进化 Agent"** 路线——让 AI 从每次交互中学习、创建技能、改进技能，同时可以在从 $5 VPS 到 GPU 集群的任意基础设施上运行，追求越用越强的智能体体验。

两者在消息渠道、技能系统、MCP 集成等方面有交集，Hermes 还提供了从 OpenClaw 迁移的内建工具。选择哪条路线，取决于你更在意"通讯覆盖广度"还是"Agent 进化深度"。

---

*数据来源：OpenClaw GitHub (openclaw/openclaw)、Hermes Agent GitHub (NousResearch/hermes-agent)，2026 年 4 月 14 日。*
