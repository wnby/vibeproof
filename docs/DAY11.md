# Day 11：结构重构

本轮不增加产品功能，专门解决平铺模块难以阅读和配置分散的问题。

## 完成内容

- 把 21 个根级业务模块重组为 `agents`、`core`、`repository`、`llm`、`runtime`、`workflows`、`reports` 和
  `interfaces` 八个职责明确的包。
- 新建 `config.py`，集中全部环境配置和默认值，并通过不可变 `Settings` 传递配置。
- 把原来单个大型 `schemas.py` 拆成七组领域模型。
- 三个子 Agent 全部收拢到 `agents/`，外部入口全部收拢到 `interfaces/`。
- 测试目录镜像生产代码结构，共享测试构造器不再从另一个测试文件导入。
- 新增 AST 架构测试，持续约束包之间的单向依赖。

## 设计原则

模型 Provider 使用 Strategy，瞬时重试使用 Decorator，SQLite 证据访问使用 Repository，完整接管使用
Coordinator/Facade。设计模式只用于表达真实边界，不建立通用框架、服务容器或多层兼容壳。
