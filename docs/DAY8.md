# Day 8: deterministic Agent Eval

Day 8 没有继续增加新的 Agent 角色，而是为已经完成的 MVP 增加可重复评估层。目标是把“命令能运行”
提升为“能够说明一次真实运行满足了哪些预期、在哪些指标上失败”。

## 实现内容

- `EvaluationCase` 和 `EvaluationExpectations`：声明一个仓库场景应该出现的结果。
- `EvaluationMetric` 和 `EvaluationReport`：保存逐项实际值、期望值和 PASS/FAIL/INFO 状态。
- `RepositoryEvaluator`：确定性检查接管、架构引用、学习引用、题目覆盖、运行状态和仓库变化。
- `ObservedModelClient`：记录分析与教学调用次数、传输失败和累计模型耗时。
- `eval` CLI：执行一次完整 Takeover，然后输出 JSON 或 Markdown Eval 报告。
- 三个固定 fixture：正常服务、已知缺陷服务、异步多组件 Agent。
- Mock 回归测试：在不请求外部模型的前提下验证评估框架和失败识别。

## 为什么不让模型自评

模型自评容易把流畅表达误当成正确，也可能接受自己虚构的文件。VibeProof Eval 首先检查能够确定性验证的
事实：类型契约、快照、引用 ID、文件路径、学习覆盖、pytest 状态和仓库是否变化。语义正确性被明确
保留为真实模型测试后的人工抽查项目，不混入自动分数。

## 已知失败也是有效样本

`broken_service` 的测试必然失败。对应 Eval 用例明确期望 `TakeoverStatus.PARTIAL` 和
`RuntimeStatus.FAILED`；系统如实记录失败时，Eval 本身为 `PASSED`。这个场景验证 VibeProof 不会为了
生成漂亮报告而吞掉负面运行证据。

## 模型测试边界

Day 8 首先使用 Mock 验证工程路径，随后通过用户提供的 OpenAI-compatible 中转站测试 Claude Sonnet
4.6 和 Claude Haiku 4.5。密钥只进入交互式临时变量，没有写入命令、报告或 Git。

## 本地验收

- 98 项自动化测试通过，其中三个固定 Eval 场景均为 `PASSED`。
- VibeProof 自评：接管 `COMPLETED`，5 条架构结论，4 个学习单元，4 道题，Eval `PASSED`。
- MindBridge：接管 `COMPLETED`，5 条架构结论，4 个学习单元，4 道题，Eval `PASSED`。
- 两个真实仓库均为计划式 Runtime，模型调用 5 次、传输失败 0 次。

以上数据来自确定性 Mock，用于证明评估框架可复现；不能替代后续中转站真实模型测试。

## 中转站真实测试结果

短 JSON 冒烟请求成功。首次完整 Sonnet Eval 暴露 `urllib` 默认请求被网关以 403/1010 拒绝；加入明确
User-Agent 后网络可用。随后真实模型返回 Markdown 包装 JSON，促成了有限结构化输出规范化层。Sonnet
最好的一次运行完成 3 次架构请求，产出 4 条有效结论；CitationReviewer 同时拒绝了 1 条没有证据的
“无外部依赖”结论，说明引用审查在真实模型下生效。

完整 Eval 最终没有通过：教学请求及后续 Haiku 请求多次在约 60 秒被中转站主动关闭。将客户端超时
提升至 180 秒、改用原生 `/v1/messages`、以及启用 OpenAI SSE 后仍能复现，表明剩余限制位于中转站
或上游首次数据之前，而非 VibeProof 的读取超时。项目如实保存 `MODEL_ERROR` 和 `FAILED` Eval，不把
部分成功包装成完整通过。
