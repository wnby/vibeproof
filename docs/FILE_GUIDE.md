# 文件职责导览

这份文档用于帮助第一次阅读 VibeProof 的开发者快速定位代码。Python 文件内部也有对应的中文模块级
说明；对于 JSON、锁文件、版本文件等不适合写注释的格式，以本导览为准。

## 根目录

- `README.md`：项目首页，介绍定位、现有能力、快速开始、安全边界和路线图。
- `pyproject.toml`：Python 包元数据、运行/开发依赖以及 pytest、Ruff、Hatch 的工具配置。
- `uv.lock`：由 uv 自动生成的精确依赖锁文件，用于本地和 CI 复现同一套环境，不应手工修改。
- `.python-version`：规定项目默认使用的 Python 版本，供 uv 和版本管理工具读取。
- `.env.example`：API 工作区和模型提供方环境变量的安全示例，不包含真实密钥。
- `.gitignore`：声明虚拟环境、本地证据库、缓存、构建物和密钥文件等不应提交的内容。
- `LICENSE`：项目采用的 MIT 开源许可证全文。

## 自动化

- `.github/workflows/ci.yml`：GitHub Actions 持续集成，固定在 Linux/Python 3.11 上安装锁定依赖，然后运行
  Ruff 和全部 pytest 测试。

## 核心包 `vibeproof/`

- `__init__.py`：包级入口和版本号声明。
- `__main__.py`：让用户可以用 `python -m vibeproof` 启动 CLI。
- `schemas.py`：全部阶段共享的 Pydantic 数据模型、状态枚举和跨字段校验。
- `scanner.py`：不执行目标代码的仓库扫描、文件分类、敏感文件跳过和快照计算。
- `source_index.py`：通过 AST 提取 Python 符号、导入关系和带行号的源码分块。
- `evidence_store.py`：在本地 SQLite 中保存、搜索和重新加载快照绑定的源码证据。
- `model_client.py`：统一 Mock、OpenAI-compatible 和 Ollama 的模型调用接口。
- `analyst.py`：受限搜索源码并生成带引用架构结论的仓库分析 Agent。
- `reporting.py`：把架构分析结果渲染为 Markdown。
- `runtime.py`：计划或显式执行固定 pytest 检查，并记录运行证据和前后快照。
- `runtime_reporting.py`：把运行计划与执行结果渲染为 Markdown。
- `learning_evidence.py`：在有限预算内为教学 Agent 选择入口、测试、依赖等代表性证据。
- `tutor.py`：根据架构与源码证据生成学习单元、练习和测验，并审查所有引用。
- `coordinator.py`：串联扫描、索引、分析、教学和运行验证，生成统一接管结果。
- `takeover_reporting.py`：把完整接管过程和各阶段产物汇总为 Markdown。
- `quiz.py`：从 JSON 接管报告生成答题模板，并负责报告和答题文件的严格解析。
- `answer_reviewer.py`：根据题目、评分点和限定源码证据评审答案，计算学习进度。
- `review_reporting.py`：把逐题评审和学习进度渲染为 Markdown。
- `evaluator.py`：按显式用例确定性评估接管状态、引用、学习覆盖和运行结果。
- `evaluation_reporting.py`：把 Eval 指标和接管摘要渲染为 Markdown。
- `cli.py`：定义全部命令行参数、业务服务调用、文件输出和退出码。
- `api.py`：提供只允许扫描配置工作区内部路径的 FastAPI 接口。

## 测试 `tests/`

- `test_schemas.py`：验证核心数据契约会拒绝矛盾状态。
- `test_scanner.py`：验证扫描结果、快照稳定性及文件读取边界。
- `test_source_index.py`：验证 AST 符号、导入、分块和文件完整性检查。
- `test_evidence_store.py`：验证 SQLite 写入、检索、引用加载和快照隔离。
- `test_model_client.py`：验证任务专用 Mock 和两类真实模型传输契约。
- `test_analyst.py`：验证分析 Agent 的动作预算、引用审查和报告输出。
- `test_runtime.py`：验证运行计划、显式执行、超时、输出与快照保护。
- `test_learning_evidence.py`：验证教学证据选择范围、预算、顺序和去重。
- `test_tutor.py`：验证学习计划、题目关系及教学引用审查。
- `test_coordinator.py`：验证统一接管的成功、部分失败和快照变化流程。
- `test_quiz.py`：验证答题模板创建、身份保留和 JSON 文件错误处理。
- `test_answer_reviewer.py`：验证语义评分、Mock 结构模式和答案引用边界。
- `test_review_reporting.py`：验证 Markdown 学习报告的关键内容。
- `test_evaluator.py`：验证 Eval 指标、用例文件和三个固定仓库场景。
- `test_cli.py`：验证各子命令和完整学习闭环的端到端行为。
- `test_api.py`：验证 API 正常扫描及工作区路径限制。

## 文档 `docs/`

- `MVP.md`：第一版 MVP 的问题定义、范围、数据流和验收标准。
- `ARCHITECTURE.md`：按开发阶段解释整体组件关系和数据流。
- `THREAT_MODEL.md`：说明目标仓库、模型输入、运行命令和敏感信息相关的安全边界。
- `DAY2.md`：记录 AST 源码索引和本地证据库的实现。
- `DAY3.md`：记录源码检索、架构分析 Agent 和引用审查。
- `DAY4.md`：记录计划优先的运行验证和执行证据。
- `DAY5.md`：记录统一接管协调器和阶段化报告。
- `DAY6.md`：记录源码证据驱动的学习计划和测验生成。
- `DAY7.md`：记录答题模板、证据化答案评审和学习进度闭环。
- `DAY8.md`：记录确定性 Agent Eval、固定场景和真实模型测试边界。
- `EVALUATION.md`：说明指标、自定义用例、中转站配置和 Eval 命令。
- `FILE_GUIDE.md`：当前文件，集中解释仓库内各文件的职责。

## 示例 `examples/`

- `mindbridge-manifest.json`：对 MindBridge 执行静态扫描后得到的真实仓库清单示例。
- `mindbridge-index-summary.json`：MindBridge AST 索引规模与本地数据库位置摘要。
- `mindbridge-analyst-summary.json`：MindBridge 架构分析和引用审查结果摘要。
- `mindbridge-learning-summary.json`：MindBridge 学习单元、问题和证据位置摘要。
- `mindbridge-takeover-summary.json`：MindBridge 一次完整计划式接管的阶段结果摘要。
- `mindbridge-review-summary.json`：MindBridge 答案文件在 Mock 结构评审模式下的验证摘要。
- `vibeproof-runtime-summary.json`：VibeProof 对自身执行 pytest 后保存的运行证据摘要。
- `quiz-submission.example.json`：说明答题文件字段结构的示例；实际使用时应通过 `quiz` 命令生成身份信息。
- `evaluation-suite-summary.json`：三个 Mock 固定评估场景的结果与真实模型待测状态。

## 评估场景 `evals/`

- `cases/healthy_service.json`：声明正常服务应完整接管并通过 pytest。
- `cases/broken_service.json`：声明已知缺陷服务应保留 FAILED 运行证据。
- `cases/ambiguous_agent.json`：声明异步多组件场景的计划式接管预期。
- `fixtures/healthy_service/app.py`：正常服务的业务函数。
- `fixtures/healthy_service/test_app.py`：正常服务的两个通过测试。
- `fixtures/broken_service/app.py`：故意保留税额计算缺陷的业务函数。
- `fixtures/broken_service/test_app.py`：稳定暴露缺陷的失败测试。
- `fixtures/ambiguous_agent/service.py`：Coordinator、Worker 和异步 gather 实现。
- `fixtures/ambiguous_agent/test_service.py`：验证异步协调结果的测试。
