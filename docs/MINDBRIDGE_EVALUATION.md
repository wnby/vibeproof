# MindBridge 真实仓库评测

这次评测用 MindBridge 验证 VibeProof 是否能接管一个中等规模的真实 Python Agent 仓库，而不只是完成
人工构造的演示项目。目标仓库包含 49 个 Python 文件，使用 FastAPI、SQLAlchemy、Redis 和事件驱动
多 Agent Runtime；评测只做静态接管和 Runtime 计划，不执行目标代码。

## 质量门槛

用例位于 `evals/cases/mindbridge.json`，要求：

- Takeover 为 `COMPLETED`，Runtime 为 `PLANNED`。
- 至少 4 条架构结论，最多 1 条被拒绝结论。
- 至少 4 个学习单元和 4 道题，每个单元都有题目。
- 架构与教学引用全部来自当前源码快照。
- 必须覆盖 `app/main.py`、`app/api/routes.py`、`app/agents/harness.py` 和
  `app/agents/event_driven_runtime.py`。
- 模型传输失败数为 0，扫描前后仓库保持不变。

## 真实失败如何推动改进

初始 Mock 只能覆盖 1/4 个关键路径。真实模型随后暴露了四类问题：

1. 模型在一次调用中连续输出多个搜索动作；Analyst 因此明确“一次模型调用只允许一个工具回合”，并把
   剩余查询和步骤预算放进状态。
2. 模型会用不同措辞反复读取同一批源码；EvidenceStore 现在跳过已观察代码块，精确路径查询只在目标
   文件内检索，并优先返回模块总览。
3. 仅靠源码片段不容易选择下一跳；索引中的静态 import 现在会解析成仓库内真实路径，供 Agent 沿
   `main → routes → service → harness → factory → runtime` 导航。
4. Tutor 曾因证据预算不对齐和 `E11、E12` 一类模型格式拒绝有效单元；教学证据预算现在覆盖 Analyst
   的完整证据上限，短别名解析只接受 `E数字` 与安全分隔符，不从普通文本中宽松提取引用。

这些改动都位于通用 Agent、检索和证据边界，没有加入 MindBridge 专用文件名分支或中转站专用补丁。

## 最终结果

2026-08-29 使用 OpenAI-compatible 的 `gpt-5.6-terra`，配置 `max_queries=6`、`max_steps=10`，最终
92.469 秒完成：

- Eval `PASSED`，Takeover `COMPLETED`。
- Architecture `COMPLETED / VERIFIED`：8 条接受结论，0 条拒绝结论。
- Learning Plan `SOURCE_GROUNDED`：5 个学习单元、5 道问题。
- 关键路径覆盖 4/4；架构引用 26/26、教学引用 34/34 均属于当前快照。
- Analyst 与 Tutor 共调用模型 8 次，传输失败 0 次。
- Runtime 为预期的 `PLANNED`，目标仓库未被修改。

脱敏机器可读摘要位于 `examples/mindbridge-real-evaluation-summary.json`。结果证明的是这一快照、模型和
线路下的一次完整成功，不代表所有仓库和每次模型采样都会稳定通过；后续应把该用例保留为真实模型回归
基准。

## 复现命令

API Key 只通过临时环境变量提供，不能写进命令参数或仓库：

```powershell
$env:VIBEPROOF_AI_API_KEY = "临时 API Key"

uv run python -m vibeproof eval D:\path\to\mindbridge-py `
  --provider openai-compatible `
  --model gpt-5.6-terra `
  --base-url https://your-relay.example/v1 `
  --case evals\cases\mindbridge.json `
  --max-queries 6 `
  --max-steps 10 `
  --format json `
  --output .vibeproof\mindbridge-evaluation.json

Remove-Item Env:VIBEPROOF_AI_API_KEY
```
