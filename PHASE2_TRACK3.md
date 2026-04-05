# Phase 2 - Track 3: 增强检索与排序

## 目标
增强检索能力，支持名称匹配锚点、锚点继承、向量召回、融合排序和关系扩展。

## 负责模块
- `app/services/retrieval/anchor_resolver.py`（扩展）
- `app/services/retrieval/retriever.py`（扩展）
- `app/services/retrieval/ranker.py`（新增）
- `app/services/retrieval/graph_expander.py`（新增）

## 任务清单

### Task 1: 名称匹配锚点
扩展 `anchor_resolver.py`，实现 `name_match` 锚点来源。

**逻辑：**
1. 从问题中提取可能的对象名称（模块名、文件名、类名、方法名）
2. 用结构化索引匹配（by name, by qualified_name）
3. 处理三种情况：
   - 唯一命中 → confidence=0.85
   - 轻度歧义（2-3个匹配）→ confidence=0.65，取最相关的
   - 多命中失败（>3个匹配）→ 降为 none

**Commit:** `feat(retrieval): implement name-based anchor matching`

### Task 2: 锚点继承
扩展 `anchor_resolver.py`，支持从上轮记忆继承锚点。

**继承条件（全部满足才继承）：**
1. 上轮锚点存在
2. 当前问题明显是追问（不包含新的文件/类/方法名）
3. 会话未明显切题

**实现：**
- 从 MemoryManager 获取上轮 AnchorMemory
- 判断是否追问（简单规则：问题长度短、包含代词"它"/"这个"/"该方法"等）
- 继承时 confidence 乘以衰减系数 0.9

**Commit:** `feat(retrieval): implement anchor inheritance from session memory`

### Task 3: 增强 Retriever 支持向量召回
扩展 `retriever.py`，在结构化召回基础上补充向量召回。

**逻辑：**
1. 结构化召回（已有）
2. 将问题文本编码为向量
3. 用 VectorStore 做相似度搜索
4. 根据锚点级别选择搜索桶：
   - symbol 锚点 → search_symbols + search_files
   - file 锚点 → search_files + search_symbols
   - module 锚点 → search_modules + search_files
   - none → search_all
5. 合并结构化和向量结果

**Commit:** `feat(retrieval): add vector-based recall to retriever`

### Task 4: 实现 Ranker
新增 `app/services/retrieval/ranker.py`，实现候选融合与重排。

**排序因子：**
- anchor_proximity: 与锚点的距离（同 symbol=1.0, 同 file=0.7, 同 module=0.4, 其他=0.1）
- name_hit: 名称命中度（精确=1.0, 部分=0.5, 无=0.0）
- type_match: 对象类型匹配度
- semantic_similarity: 向量相似度（来自向量召回）
- graph_distance: 图距离（一跳=0.8, 二跳=0.4）
- memory_weight: 记忆加权（最近使用过的对象加分）

**输出：** top-k 统一候选列表

**Commit:** `feat(retrieval): implement candidate ranking with multi-factor scoring`

### Task 5: 实现 GraphExpander
新增 `app/services/retrieval/graph_expander.py`，实现关系扩展。

**支持的扩展：**
- callers（谁调用了我）
- callees（我调用了谁）
- depends_on（我依赖谁）
- reverse_depends_on（谁依赖我）
- references（引用关系）

**规则：**
- 默认只扩一跳
- 二跳扩展需满足：expansion_gain >= EXPANSION_GAIN 阈值
- expansion_gain 计算：新增对象中与问题相关的比例

**Commit:** `feat(retrieval): implement graph-based relation expansion`

### Task 6: 集成与测试
更新 QAAgent 使用增强后的检索流程，添加单元测试。

**Commit:** `feat(retrieval): integrate enhanced retrieval into QA pipeline`

## 验收标准
1. 可以通过名称问问题（不需要选择代码片段）
2. 支持追问（锚点继承）
3. 向量召回补充结构化结果
4. 排序结果合理
5. 关系扩展正确
6. 有单元测试
