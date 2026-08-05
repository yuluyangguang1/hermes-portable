# 配置中心 · 下一轮任务（2026-08-05 定）

## 本轮（已完成，未发版）
- 上游 provider 同步：加 upstage（Solar）+ qwen-oauth，commit 2ef76ae5f
- 未推 origin、未打 tag（发版待定）

## 下一轮
1. **单独做「自定义 base_url 输入字段」功能**
   - 目的：让 provider 可填 per-resource base_url（当前 PROVIDERS 无此 UI 字段）
   - 涉及：前端表单 + 后端 save 处理 + /api/test 回退已支持 base（之前修过）
2. **加 3 个上游 provider**（依赖上面的 base_url 字段）
   - bedrock：AWS SDK 凭证，无静态模型，base=bedrock-runtime.us-east-1.amazonaws.com，env=空(AWS凭证)
   - vertex：OAuth2 服务账号，无静态模型，base 运行时算，env=空
   - azure-foundry：env=AZURE_FOUNDRY_API_KEY + AZURE_FOUNDRY_BASE_URL，base 空(用户填)
   - 这 3 个上游有但无静态模型列表，硬加会半成品，必须先有 base_url 自定义

## A 部分还余（可选，未排期）
- 上游 config 开关加 UI：session_reset / tool_loop_guardrails / memory nudge·flush
- 需确认 Hermes 本体 config schema 兼容性
