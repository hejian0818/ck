CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    object_id VARCHAR(255) NOT NULL,
    object_type VARCHAR(50) NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repo_id, object_id)
);

CREATE INDEX IF NOT EXISTS embeddings_vector_idx
ON embeddings
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS embeddings_type_idx
ON embeddings(object_type);
