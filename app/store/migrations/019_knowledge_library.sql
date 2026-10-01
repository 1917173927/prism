CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    visibility TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    subject TEXT,
    period TEXT,
    published_at TEXT NOT NULL,
    deleted_at TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_document_versions (
    document_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (document_id, revision)
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    page INTEGER,
    paragraph INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding_json TEXT,
    embedding_model TEXT,
    embedding_revision TEXT
);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_scope ON knowledge_documents(owner_id, visibility, published_at);
CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_version ON knowledge_chunks(document_id, revision);
CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
