# Phase 3 - Track 2: 段落生成与 PlantUML 图表

## 目标
实现段落内容生成和 PlantUML 图表自动生成，产出完整的设计文档。

## 负责模块
- `app/services/agents/doc_agent.py`（扩展）
- `app/services/diagrams/plantuml_generator.py`（新增）
- `app/services/context/doc_context_builder.py`（新增）

## 前置依赖
- Phase 3 Track 1（文档模型 + 骨架规划 + 段落检索）

## 任务清单

### Task 1: 文档上下文构建器
新增 `app/services/context/doc_context_builder.py`，为每个段落构建 LLM 提示。

**逻辑：**
1. 根据 SectionPlan 和检索结果组装上下文
2. 不同 section_type 使用不同提示模板：
   - overview: 列出所有模块、各模块摘要、整体架构描述
   - module: 模块职责、包含文件列表、关键符号签名和摘要
   - api: API 路由列表、请求/响应模型、调用链
   - data_flow: 数据流转路径、关键调用链
   - dependency: 模块间依赖关系、外部依赖
   - summary: 总结要点
3. 限制上下文长度，优先保留高分对象

**Commit:** `feat(doc): implement document context builder with section templates`

### Task 2: 段落内容生成
在 `doc_agent.py` 中实现逐段落生成。

**逻辑：**
1. 遍历骨架中的每个 SectionPlan
2. 用 DocRetriever 检索段落上下文
3. 用 DocContextBuilder 构建提示
4. 调用 LLM 生成 Markdown 内容
5. 后处理：标题级别对齐、代码块格式化

**生成控制：**
- 每个段落独立生成���支持重试
- 段落生成失败时标注 confidence=0，不阻塞整体
- 支持并行生成（未来优化）

**Commit:** `feat(doc): implement section-by-section document generation`

### Task 3: PlantUML 图表生成器
新增 `app/services/diagrams/plantuml_generator.py`，自动生成设计图。

**支持的图表类型：**
1. **模块依赖图（component diagram）：**
   - 每个 module 一个组件
   - 跨模块关系用箭头连接
   - 标注依赖类型

2. **类关系图（class diagram）：**
   - 从指定模块/文件内的 symbol 提取
   - class/interface 为类节点
   - 继承、实现、关联关系

3. **调用流程图（sequence diagram）：**
   - 从指定入口符号出发
   - 沿 calls 关系生成调用序列
   - 最多展开 3 层

**入口：**
```python
class PlantUMLGenerator:
    def generate_component_diagram(self, modules: list[Module], relations: list[Relation]) -> str
    def generate_class_diagram(self, symbols: list[Symbol], relations: list[Relation]) -> str
    def generate_sequence_diagram(self, entry_symbol: Symbol, call_chain: list[Relation]) -> str
```

**输出格式：** PlantUML 源码字符串（@startuml ... @enduml）

**Commit:** `feat(diagrams): implement PlantUML diagram generation`

### Task 4: 图表与段落集成
将图表生成集成到文档生成流程中。

**自动图表规则：**
- overview 段落 → 生成模块依赖图
- module 段落 → 如果模块内有 class/interface，生成类关系图
- api/data_flow 段落 → 如果有调用链，生成调用流程图

**集成点：**
- DocAgent 在生成段落内容后，检查是否需要图表
- 图表代码嵌入到 SectionContent.diagrams 中
- 最终文档中图表以 PlantUML 代码块形式嵌入

**Commit:** `feat(doc): integrate PlantUML diagrams into document generation`

### Task 5: 测试
- 上下文构建测试（各 section_type 模板）
- PlantUML 生成测试（每种图表类型）
- 端到端文档生成测试（骨架 → 段落 → 图表）

**Commit:** `test: add tests for document generation and PlantUML diagrams`

## 验收标准
1. 每个段落能生成合理的 Markdown 内容
2. PlantUML 图表语法正确
3. 图表与段落内容匹配
4. 文档整体结构完整、可读
5. 有单元测试覆盖
