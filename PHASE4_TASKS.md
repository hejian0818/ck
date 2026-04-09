# Phase 4: 生产就绪

## 目标
完善系统的生产化能力：高级降级、全面日志、缓存优化、配置管理、演示和文档。

## 任务清单

### Task 1: 高级降级模式
扩展 QA Agent 和 Doc Agent 的降级逻辑。

**QA 降级增强：**
- 部分回答模式：能回答的部分正常回答，不确定的部分标注
- 多候选回答：当检索结果分散时，列出多个可能答案
- 引导式追问：根据当前上下文主动建议用户追问的方向

**Doc 降级增强：**
- 段落级降级：单个段落失败不影响整体文档
- 占位符段落：生成失败的段落用 "TODO: 需要补充" 占位
- 低置信度标注：对生成信心不足的段落标注 "[Low Confidence]"

**Commit:** `feat: implement advanced degradation modes for QA and doc agents`

### Task 2: 全面日志与指标
扩展结构化日志，添加可观测性。

**日志增强：**
- 每次 QA 请求记录完整链路（锚点 → 检索 → 策略 → 生成 → 响应）
- 每次文档生成记录段落级进度
- 向量搜索记录查询向量维度、返回数量、最高/最低相似度
- LLM 调用记录 token 使用量、延迟

**指标采集：**
- 请求延迟分布
- 策略使用分布（S1/S2/S3/S4 比例）
- 降级率
- 向量搜索命中率
- LLM 调用成功率

**Commit:** `feat: add comprehensive logging and metrics collection`

### Task 3: 缓存优化
减少重复计算和 IO。

**缓存策略：**
- 向量编码缓存：相同文本的嵌入向量缓存（LRU, maxsize=1000）
- 图对象缓存：GraphRepository 查询结果短期缓存（TTL=60s）
- LLM 响应缓存：相同问题+相同上下文的回答缓存（可选）

**实现：**
- 使用 `functools.lru_cache` 或自定义 TTL 缓存
- 缓存命中率纳入日志指标

**Commit:** `feat: add caching layer for embeddings, graph queries, and LLM responses`

### Task 4: 配置管理完善
补充所有可配置项，支持环境变量覆盖。

**新增配置项：**
- DOC_MAX_SECTIONS: 文档最大段落数 (default: 50)
- DOC_SECTION_MAX_TOKENS: 单段落最大 token 数 (default: 2000)
- DOC_DIAGRAM_ENABLED: 是否生成图表 (default: true)
- CACHE_EMBEDDING_SIZE: 嵌入缓存大小 (default: 1000)
- CACHE_GRAPH_TTL: 图查询缓存 TTL (default: 60)
- LLM_MAX_RETRIES: LLM 调用最大重试次数 (default: 3)
- LLM_TIMEOUT: LLM 调用超时 (default: 30s)

**Commit:** `feat: complete configuration management with all tunable parameters`

### Task 5: Demo 脚本
创建 `scripts/demo.py`，提供端到端演示。

**演示流程：**
1. 扫描一个示例仓库（可以用本项目自身）
2. 构建图索引
3. 生成向量嵌入
4. 运行 QA 问答示例
5. 生成设计文档
6. 输出文档到 `data/output/`

**Commit:** `feat: add end-to-end demo script`

### Task 6: README 和最终测试
完善项目文档和测试覆盖。

**README 内容：**
- 项目介绍
- 快速开始（安装、配置、运行）
- API 文档
- 架构说明
- 配置参考

**测试补充：**
- API 端点集成测试
- 端到端测试（扫描 → 索引 → QA）
- 降级场景测试

**Commit:** `docs: update README and add final integration tests`

## 验收标准
1. 降级模式不会产生错误或异常
2. 日志可追踪完整请求链路
3. 缓存显著减少重复 IO
4. 所有配置项有默认值且可覆盖
5. Demo 脚本可一键运行
6. README 完整可读
7. 测试覆盖关键路径
