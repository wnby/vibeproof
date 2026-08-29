# Agent Eval 指南

VibeProof 的 Eval 用来回答一个具体问题：一次仓库接管是否满足事先声明的工程期望。评估器只读取类型化
接管产物，不调用另一个模型给原模型打分，因此同一份报告和用例会得到相同结果。

## 快速运行

对任意仓库执行默认的计划式评估：

```powershell
uv run python -m vibeproof eval D:\projects\demo `
  --provider mock `
  --format markdown `
  --output reports\evaluation.md
```

默认用例期望接管状态为 `COMPLETED`、运行状态为 `PLANNED`，并要求至少一条架构结论、一个学习单元和
一道测验题。只有加上 `--execute` 才会运行固定的 pytest 检查；未指定用例时，执行模式会自动期望
`PASSED`。

## 固定场景

仓库内置三类可重复场景：

- `healthy_service`：两个测试通过，用于验证完整成功路径。
- `broken_service`：业务代码故意保留缺陷，pytest 失败才是正确结果。
- `ambiguous_agent`：包含 Coordinator、Worker 和异步 gather，用于验证多组件学习覆盖。

例如运行正常场景：

```powershell
uv run python -m vibeproof eval evals\fixtures\healthy_service `
  --case evals\cases\healthy_service.json `
  --provider mock --execute --python .venv\Scripts\python.exe
```

已知缺陷场景的 `TakeoverReport` 应为 `PARTIAL`、Runtime 应为 `FAILED`，但最终 Eval 应为 `PASSED`，因为
系统准确观察到了用例声明的失败，而不是把测试失败隐藏成成功。

## 指标

当前评估器检查：

- 接管状态是否符合用例预期。
- 架构 Agent 是否返回合法的完成结果。
- 接受和拒绝的架构结论数量。
- 架构结论引用是否全部属于当前源码快照。
- 学习计划是否为 `SOURCE_GROUNDED`。
- 学习单元和测验题数量是否达标。
- 每个学习单元是否至少有一道题。
- 学习单元和问题是否都引用当前快照证据。
- 用例指定的关键源码路径是否被观察到。
- Runtime 状态是否符合预期。
- 执行前后仓库是否保持不变。
- 分析和教学模型的调用次数、传输失败次数及累计耗时。
- 各工作流阶段完成和失败数量。

这些指标能验证结构化输出、证据来源和工作流行为，但不能自动证明模型对源码含义的解释完全正确。
真实模型测试仍需要人工抽查结论内容，后续才适合逐步建立人工标注的语义基准集。

## 中转站 API 测试

中转站需要提供 OpenAI-compatible Chat Completions 接口。配置只通过当前终端环境变量传递：

```powershell
$env:VIBEPROOF_AI_PROVIDER = "openai-compatible"
$env:VIBEPROOF_AI_MODEL = "中转站提供的模型名"
$env:VIBEPROOF_AI_BASE_URL = "https://中转站地址/v1"
$env:VIBEPROOF_AI_API_KEY = "临时 API Key"
$env:VIBEPROOF_AI_TIMEOUT_SECONDS = "180"

uv run python -m vibeproof eval D:\projects\demo `
  --provider openai-compatible `
  --format json `
  --output .vibeproof\real-model-evaluation.json
```

API Key 不接受命令行参数，也不会写入报告。测试结束后可以清除当前终端变量：

```powershell
Remove-Item Env:VIBEPROOF_AI_API_KEY
```

真实模型验收时至少检查 Eval 指标、模型输出内容、耗时、失败阶段和被拒绝引用；不能只看命令退出码。

### 星辰 AI 实测记录

`https://ai.centos.hk/v1` 同时暴露 OpenAI Chat Completions 和 Anthropic Messages。测试过
`claude-sonnet-4-6` 与 `claude-haiku-4-5-20251001`，未记录 API Key。

- 短 JSON 请求成功，证明地址、Key 和模型名可用。
- Python 默认 User-Agent 会被返回 403/1010，现已改为明确的 VibeProof User-Agent。
- Sonnet 会输出 Markdown 包装 JSON，现由有限规范化层提取后继续执行严格 Pydantic 校验。
- 最佳 Sonnet 架构运行接受 4 条有证据结论，并拒绝 1 条无证据结论。
- 教学阶段和其他复杂请求可能在约 60 秒被中转站关闭；180 秒客户端超时、原生 Anthropic 端点和 SSE
  都不能消除首次响应数据之前的上游关闭。

因此本次真实 Eval 为部分成功而非端到端通过。再次测试前应先向中转站确认长推理请求、首字节超时和
流式转发策略，或选择能够在该网关首字节限制内稳定响应的模型线路。

### gpt-5.6-terra 实测记录

2026-08-28 使用优化线路 `https://frapi.centos.hk/v1` 测试 `gpt-5.6-terra`，未记录 API Key。
早期尝试暴露了两个独立问题：SSE 末尾包含仅有 usage 的空 choices 事件，以及模型无法稳定复制完整
`chunk:sha256` 引用。项目没有增加中转站专用分支，而是调整了通用 Agent 接口：

- 从 Pydantic 输出模型生成 `json_schema`，通过 `strict=true` 约束 Analyst、Tutor 和 Reviewer。
- 同步 ``complete`` 工作流默认使用非流式响应；SSE 仍作为可选传输实现保留。
- 模型上下文使用 `E1`、`E2` 等短证据别名，返回后再确定性恢复完整 chunk ID。
- SSE 解析器接受 OpenAI-compatible 服务合法的 usage-only 结束事件。

最终对 `healthy_service` 执行完整 Takeover，46.6 秒后以退出码 0 完成：

- Takeover 为 `COMPLETED`。
- Architecture 为 `COMPLETED / VERIFIED`，接受 4 条结论，拒绝 0 条。
- Learning Plan 为 `SOURCE_GROUNDED`，生成 4 个学习单元和 4 道问题，拒绝 0 项。
- Runtime pytest 为 `PASSED`，执行前后仓库快照保持一致。

这次实测验证的是完整 Agent 数据流，而不只是一个短模型请求。后续真实模型回归仍应通过 Eval 用例记录
模型、线路、耗时、引用完整性和阶段状态，避免把一次成功当作长期稳定性结论。

## 自定义用例

`--case` 接受严格 JSON，主要字段如下：

```json
{
  "schema_version": "1.0",
  "case_id": "my-service",
  "name": "My service expectations",
  "description": "Why this case exists.",
  "expectations": {
    "expected_takeover_status": "COMPLETED",
    "expected_runtime_status": "PLANNED",
    "minimum_claims": 2,
    "maximum_rejected_claims": 0,
    "minimum_learning_units": 2,
    "minimum_quiz_questions": 2,
    "maximum_model_failures": 0,
    "required_evidence_paths": ["app.py", "tests/test_app.py"],
    "require_source_grounded_learning": true,
    "require_unit_question_coverage": true,
    "require_current_snapshot_citations": true,
    "require_unchanged_repository": true
  }
}
```

如果任意强制指标失败，Eval 状态和 CLI 退出码都会失败，适合后续接入 CI 或模型回归比较。
