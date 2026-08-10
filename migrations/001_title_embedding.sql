-- articles.title_embedding + IVFFlat (pgvector)
-- 사전 조건: 서버에 pgvector 바이너리 설치 후
--   CREATE EXTENSION 가능해야 함 (Windows PG18: vector.dll + share/extension/*)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS title_embedding vector(1536);

-- 이미 있으면 스킵 (PostgreSQL 에는 CREATE INDEX IF NOT EXISTS 지원)
CREATE INDEX IF NOT EXISTS idx_articles_title_embedding
    ON articles
    USING ivfflat (title_embedding vector_cosine_ops)
    WITH (lists = 10);

COMMENT ON COLUMN articles.title_embedding IS
    '제목 임베딩 (예: 1536-dim). NULL=미계산. 유사 검색·중복 묶기용';
