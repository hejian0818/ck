# Phase 2 - Track 4: 记忆与状态机

## 目标
扩展记忆管理，实现指标计算和四状态状态机，支持策略自动切换和降级。

## 负责模块
- `app/services/memory/memory_manager.py`（扩展）
- `app/services/agents/qa_agent.py`（扩展）
- `app/services/agents/strategy.py`（新增）
- `app/services/agents/metrics.py`（新增）

## 任务清单

### Task 1: 扩展 MemoryManager
扩展记忆管理，支持四类记忆。

**Retrieval Memory:**
- recent_object_ids: List[str]（最近检索过的对象 ID）
- recent_subgraph_summary: str（最近局部子图摘要）
- recent_evidence_summary: str（最近证据摘要）
- 锚点变化过大时清空旧子图

**Focus Memory:**
- current_focus: str（当前焦点话题）
- 主题延续则保留，切换则覆盖或衰减

**更新规则：**
- Anchor Memory: 新锚点覆盖旧锚点，none 不覆盖强锚点
- Retrieval Memory: 最新局部子图覆盖旧子图
- Focus Memory: 主题延续保留，切换衰减

**Commit:** `feat(memory): extend memory manager with retrieval and focus memory`

### Task 2: 实现指标计算
新增 `app/services/agents/metrics.py`，计算五个指标。

**A - 锚点置信度:**
直接取 anchor.confidence

**C - 首轮召回集中度:**
- 统计 top-k 结果中最集中的 module/file 占比
- C = max(module_concentration, file_concentration)

**E - 证据充分度:**
- 基于检索结果的数量和质量
- E = min(1.0, (matched_objects * relevance_avg) / required_threshold)

**G - 扩展收益:**
- 扩展后新增的相关对象比例
- G = new_relevant_objects / total_expanded_objects

**R - 结果一致性:**
- 检索结果内部一致性
- R = 1.0 - (module_entropy / max_entropy)

**所有阈值从 thresholds.py 读取。**

**Commit:** `feat(agents): implement A/C/E/G/R metrics calculation`

### Task 3: 实现四状态状态机
新增 `app/services/agents/strategy.py`，实现策略切换。

**S1 默认路径:**
条件：A >= 0.80 且 E >= 0.60
执行：当前对象 + 一跳关系，直接回答

**S2 增强路径:**
条件：A >= 0.60 且 E < 0.60 且 C >= 0.45
执行：补向量召回 + 关系扩展，必要时二跳

**S3 反推路径:**
条件：A < 0.60 且无锚点首轮检索后 C >= 0.55
执行：反推弱锚点，再做局部证据补足

**S4 降级路径:**
触发任一：A < 0.40 或 C < 0.35 或 E < 0.40 或 R < 0.40 或 G < 0.25
执行：多中心回答 / 局部可确认回答 / 要求补充上下文

**实现：**
```python
class StrategyRouter:
    def determine_strategy(self, metrics: Metrics) -> Strategy:
        """根据指标选择策略"""
        pass

    def execute_strategy(self, strategy: Strategy, context: ...) -> ...:
        """执行选定策略"""
        pass
```

**Commit:** `feat(agents): implement four-state strategy router`

### Task 4: 实现降级处理
在 QAAgent 中实现降级逻辑。

**降级回答类型：**
1. 多中心回答：检索结果分散时，列出多个可能相关的对象
2. 局部可确认回答：只回答能确认的部分，标注不确定的部分
3. 要求补充上下文：提示用户选择具体代码片段或缩小范围

**QAResponse 扩展：**
- strategy_used: str（S1/S2/S3/S4）
- metrics: Metrics（A/C/E/G/R 值）
- degraded: bool（是否降级）
- suggestions: List[str]（补充建议）

**Commit:** `feat(agents): implement degradation handling in QA agent`

### Task 5: 更新 QAAgent 集成状态机
重构 QAAgent.answer() 方法，集成完整流程。

**完整流程：**
1. 确定锚点
2. 读取记忆
3. 计算初始指标（A）
4. 选择策略
5. 执行策略对应的检索流程
6. 计算完整指标（A/C/E/G/R）
7. 如需降级，切换到 S4
8. 组装上下文
9. 调用 LLM 生成回答
10. 回写记忆
11. 日志记录所有指标和策略

**日志要求：**
```json
{
  "session_id": "...",
  "anchor": {"level": "symbol", "confidence": 0.85},
  "metrics": {"A": 0.85, "C": 0.72, "E": 0.68, "G": 0.45, "R": 0.81},
  "strategy": "S1",
  "degraded": false,
  "used_objects": ["S_xxx", "F_yyy"],
  "elapsed_ms": 230
}
```

**Commit:** `feat(agents): integrate strategy router and metrics into QA agent`

### Task 6: 测试
添加测试覆盖：
- 指标计算测试
- 状态机路由测试（每种策略至少一个 case）
- 降级处理测试
- 记忆更新测试

**Commit:** `test: add tests for metrics, strategy router, and memory management`

## 验收标准
1. 指标计算正确
2. 状态机根据指标正确路由
3. 降级时不高置信乱答
4. 记忆正确更新（追问时继承，切题时清空）
5. 日志包含完整的指标和策略信息
6. 有单元测试覆盖
