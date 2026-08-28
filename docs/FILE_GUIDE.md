# 文件职责导航

第一次阅读 VibeProof 时，建议按照 `config → core → repository → llm → agents → workflows → interfaces` 的顺序。
每个目录只承担一类职责，业务依赖保持单向。

## `vibeproof/` 代码包

### 根入口

- `config.py`：集中定义全部环境变量、默认路径、模型地址、超时和重试配置；生成不可变 `Settings`。
- `__main__.py`：把 `python -m vibeproof` 转交给 CLI。
- `__init__.py`：声明包版本。

### `core/models/` 数据契约

这里只包含 Pydantic 模型和状态枚举，不访问文件、数据库、网络或模型。

- `common.py`：严格模型基类以及跨阶段共享的状态枚举。
- `repository.py`：仓库快照、文件清单、源码符号、代码块和引用证据。
- `analysis.py`：Agent 动作、分析结论、执行轨迹和架构报告。
- `learning.py`：学习计划、题目、答题提交、评审结果和学习进度。
- `runtime.py`：运行计划、执行证据和运行验证报告。
- `takeover.py`：完整接管流程的阶段记录和汇总报告。
- `evaluation.py`：Eval 用例、指标、模型调用摘要和评估报告。
- `__init__.py`：统一导出公共模型，让业务模块不需要记住具体模型文件。

### `repository/` 仓库证据能力

- `scanner.py`：静态扫描仓库、分类文件并计算稳定快照，不执行目标代码。
- `index.py`：使用 AST 提取 Python 符号、导入关系和带行号源码块。
- `store.py`：通过 SQLite 保存和检索快照绑定的证据，实现 Repository 模式。
- `learning_evidence.py`：在有限预算内为 Tutor 选择代表性学习证据。

### `llm/` 模型边界

- `client.py`：定义 `ModelClient` Strategy，包含 Mock、OpenAI-compatible、Ollama Provider 和重试 Decorator。
- `structured_output.py`：提取模型返回的单个 JSON 对象，再交给 Pydantic 校验。

### `agents/` 子 Agent

- `analyst.py`：按动作预算检索源码，生成带引用的架构结论，并审查引用。
- `tutor.py`：根据已验证证据生成学习单元、练习和题目。
- `reviewer.py`：根据题目、评分点和限定源码证据评审用户答案。
- `__init__.py`：公开三个 Agent 及其 Policy，打开目录即可看到全部 Agent。

### `runtime/` 运行验证

- `verifier.py`：生成固定 pytest 命令计划；只有显式开启时才执行并记录前后快照。

### `workflows/` 用户用例

- `takeover.py`：`TakeoverCoordinator` 依次协调扫描、索引、分析、教学、运行验证和报告产物。
- `evaluation.py`：执行确定性质量门槛，区分 Agent 失败与“如实发现目标缺陷”。
- `quiz.py`：创建答题模板并严格读取报告与提交文件。

### `reports/` 展示层

- `architecture.py`：架构报告 Markdown。
- `takeover.py`：完整接管报告 Markdown。
- `runtime.py`：运行验证 Markdown。
- `review.py`：答题评审和学习进度 Markdown。
- `evaluation.py`：Eval 指标 Markdown。

### `interfaces/` 外部入口

- `cli.py`：命令参数、用例调用、文件输出与退出码。
- `api.py`：FastAPI 路由与请求模型，只负责把 HTTP 请求翻译为工作流调用。

### `web/` 浏览器界面

- `index.html`：页面结构。
- `styles.css`：白色主题与布局。
- `app.js`：调用 Takeover API、消费报告并渲染 Agent 活动和证据。
- `favicon.svg`：站点图标。

## `tests/` 测试结构

测试目录镜像生产包：`agents/`、`core/`、`interfaces/`、`llm/`、`repository/`、`reports/`、`runtime/`、
`workflows/`。`test_architecture.py` 使用 AST 检查包依赖方向，并保证所有公开类、函数和方法都有导航型说明；
`test_config.py` 验证集中配置，`support.py` 只保存跨模块共享的最小测试场景构造器。

## 其他目录

- `evals/`：健康、故障和异步多组件三类固定评估场景及其显式期望。
- `examples/`：脱敏的扫描、接管、学习、运行和真实模型测试摘要。
- `docs/`：MVP、架构、威胁模型、评估指南和每日开发记录。
- `.github/workflows/ci.yml`：在 GitHub Actions 中运行 Ruff 和全部 pytest。
- `.env.example`：配置模板，不包含真实密钥。
- `pyproject.toml` / `uv.lock`：项目元数据与可复现依赖。
