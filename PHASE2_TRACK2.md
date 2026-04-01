# Phase 2 - Track 2: 向量索引

## 目标
使用 pgvector 构建向量索引，支持语义检索。

## 负责模块
- `app/services/indexing/embedding_builder.py`
- `app/storage/vector_store.py`

## 任务清单

### Task 1: 配置 pgvector 表结构
创建向量存储表。

**SQL Schema (`app/storage/schema_vector.sql`):**
```sql
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 向量索引表（按对象类型分桶）
CREATE TABLE embeddings (
    id SERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    object_id VARCHAR(255) NOT NULL,  -- module_id/file_id/symbol_id/relation_id
    object_type VARCHAR(50) NOT NULL,  -- module/file/symbol/relation
    embedding vector(768),  -- 向量维度，根据编码模型调整
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repo_id, object_id)
);

-- 创建 HNSW 索引加速相似度搜索
CREATE INDEX embeddings_vector_idx ON embeddings
USING hnsw (embedding vector_cosine_ops);

-- 按对象类型索引
CREATE INDEX embeddings_type_idx ON embeddings(object_type);
```

**实现:**
- 在 `app/storage/repositories.py` 添加 `init_vector_tables()` 方法
- 在项目初始化时自动创建表和索引

**Commit:** `feat(storage): add pgvector schema for embeddings`

---

### Task 2: 实现 EmbeddingBuilder
实现摘要向量化。

**模块:** `app/services/indexing/embedding_builder.py`

**核心类:**
```python
class EmbeddingBuilder:
    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5"):
        """初始化编码模型"""
        # 使用 sentence-transformers 或直接调用 API
        pass

    def encode_summary(self, summary: str) -> List[float]:
        """将摘要编码为向量"""
        pass

    def build_embeddings(self, graphcode: GraphCode) -> List[Embedding]:
        """为所有对象生成向量"""
        pass
```

**实现要点:**
1. 编码模型选择：
   - 本地：sentence-transformers (BAAI/bge-base-en-v1.5)
   - API：OpenAI embeddings API（兼容接口）
2. 批量编码优化（batch_size=32）
3. 向量归一化（用于 cosine 相似度）
4. 错误处理（编码失败时记录日志，跳过该对象）

**依赖添加 (pyproject.toml):**
```toml
sentence-transformers = "^2.2.0"  # 或使用 API
torch = "^2.0.0"  # sentence-transformers 依赖
```

**Commit:** `feat(indexing): implement embedding builder with sentence-transformers`

---

### Task 3: 实现 VectorStore
实现向量存储和检索。

**模块:** `app/storage/vector_store.py`

**核心类:**
```python
class VectorStore:
    def __init__(self, db_url: str):
        """初始化数据库连接"""
        pass

    def save_embeddings(self, embeddings: List[Embedding]):
        """批量保存向量"""
        pass

    def search_similar(
        self,
        query_vector: List[float],
        object_type: Optional[str] = None,
        top_k: int = 10,
        min_similarity: float = 0.5
    ) -> List[SearchResult]:
        """相似度搜索"""
        pass

    def get_embedding(self, object_id: str) -> Optional[List[float]]:
        """获取对象的向量"""
        pass
```

**实现要点:**
1. 使用 pgvector 的 cosine 距离：`embedding <=> query_vector`
2. 支持按对象类型过滤
3. 返回结果包含：object_id, similarity, object_type
4. 批量插入优化（使用 executemany）

**SQL 查询示例:**
```sql
SELECT object_id, object_type, 1 - (embedding <=> %s) as similarity
FROM embeddings
WHERE repo_id = %s
  AND object_type = %s  -- 可选
  AND 1 - (embedding <=> %s) >= %s  -- min_similarity
ORDER BY embedding <=> %s
LIMIT %s;
```

**Commit:** `feat(storage): implement vector store with pgvector`

---

### Task 4: 按对象类型分桶存储
优化向量索引结构。

**实现:**
1. 在 `VectorStore.search_similar()` 中支持 `object_type` 参数
2. 创建辅助方法：
   - `search_modules(query_vector, top_k)`
   - `search_files(query_vector, top_k)`
   - `search_symbols(query_vector, top_k)`
   - `search_relations(query_vector, top_k)`
3. 在 `Retriever` 中根据锚点级别选择搜索桶

**优化点:**
- 不同对象类型可能需要不同的 top_k
- Module 搜索：top_k=5
- File 搜索：top_k=10
- Symbol 搜索：top_k=20
- Relation 搜索：top_k=15

**Commit:** `feat(storage): add type-specific vector search methods`

---

### Task 5: 集成到索引构建流程
修改 `app/services/cleanarch/graph_builder.py`，在生成摘要后自动构建向量索引。

**修改点:**
1. 在 `build_graph()` 中调用 `EmbeddingBuilder`
2. 将向量保存到 `VectorStore`
3. 添加进度日志（"Generating embeddings for 150 objects..."）
4. 添加性能统计（编码耗时、保存耗时）

**更新 CLI (`scripts/build_index.py`):**
```python
# 构建索引
graphcode = builder.build_graph(repo_path)

# 生成摘要
summary_builder.build_summaries(graphcode)

# 生成向量
embedding_builder = EmbeddingBuilder()
embeddings = embedding_builder.build_embeddings(graphcode)

# 保存向量
vector_store.save_embeddings(embeddings)
```

**Commit:** `feat(indexing): integrate embedding generation into build pipeline`

---

## 验收标准
1. ✅ pgvector 表结构创建成功
2. ✅ 可以为测试仓库的所有对象生成向量
3. ✅ 向量存储到数据库
4. ✅ 可以执行相似度搜索
5. ✅ 按对象类型分桶搜索正常工作
6. ✅ 有单元测试覆盖 EmbeddingBuilder 和 VectorStore

## 技术要求
- 向量维度可配置（默认 768）
- 支持本地模型和 API 两种方式
- 批量操作优化性能
- 错误处理完善
- 日志记录详细

## 性能目标
- 1000 个对象编码时间 < 30 秒（本地模型）
- 相似度搜索响应时间 < 100ms
- 批量插入 1000 个向量 < 5 秒
