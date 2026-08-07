# 更新说明 (Changelog)

## v1.20.2 (2026-08-07)

配置中心多轮审计 + 修复,重点解决「能配置但配不对」的真实阻断 bug。

### 功能新增
- **模型名搜索**:在 provider 模型下拉上方加搜索框,输入即按子串过滤模型列表(OpenRouter 70+ 模型等不再难找)。无静态模型列表的 provider(custom / bedrock / vertex 等)保留自由输入,不显示搜索框。
- **主操作栏三连**:`[测试连接][保存][启动]` 统一带 Tabler 图标、等宽、loading 态(点击显示 spinner + 文案),呼应 onboarding 三步流程。去除了 provider 卡内重复的测试按钮。

### Bug 修复
- **厂商搜索 / 标签筛选失效**:搜索框与筛选标签调用的函数名拼写错误(指向不存在的 `renderProviderGrid`),修正为 `renderProviders()`,搜索与筛选恢复正常。
- **Web UI 启动按钮 404**:`/api/webui/start` 前端发 GET 而后端仅注册 POST,修正为 POST,启动按钮可用。
- **渠道配置无法正确保存**:前端 CHANNELS 字段与后端严重错位(7 处),现已全部对齐 —— discord 移除多余的 APP_ID;slack `APP_TOKEN`→`SLACK_SIGNING_SECRET`;whatsapp 两字段→`WHATSAPP_ENABLED` 单字段;weixin `ENCODING_AES_KEY`→`WEIXIN_ACCOUNT_ID`;email `USERNAME`→`EMAIL_ADDRESS`;signal `API_URL`→`SIGNAL_CLI_PATH`;matrix `USER_ID`/`PASSWORD`→`MATRIX_USER`/`MATRIX_TOKEN`。
- **upstage / qwen-oauth 无法配置**:后端 PROVIDERS 缺失这两个 provider,补齐后与前端对齐(env 可由界面填写、保存可写入 .env)。
- **渠道关闭时字段面板不收起**:修正为关闭即收起。
- **写路由潜在 404**:`_dispatch_post` 补上 query string 剥离,与 GET 侧一致。

### 样式 / 体验
- Tabler 图标本地化(离线可用,消除 CDN 阻塞)。
- 内置 LXGW WenKai 衬线字体子集(离线渲染中文标题)。
- 终端母题贯穿(.env 预览面板改为终端窗口风格)。
- 次级文字改用 AA 合规 muted 色;模态框 a11y(role/aria/Esc/焦点陷阱);开关键盘焦点可见;动效编排(tab 淡入 / 模态 pop,尊重 reduced-motion)。
- 三连按钮边框统一、hover 不再消失。

---

## v1.20.1 (2026-08-06)

- 新增 upstage + qwen-oauth provider(前端)
- web-ui 相关 7 处 bug 修复
- 配置中心基础可用版本
