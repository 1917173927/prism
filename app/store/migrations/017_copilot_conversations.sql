CREATE TABLE copilot_conversations (
    conversation_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_copilot_conversations_owner_updated
    ON copilot_conversations (owner_id, updated_at DESC, conversation_id DESC);

CREATE TABLE copilot_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED')),
    context_scope TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES copilot_conversations(conversation_id) ON DELETE CASCADE,
    UNIQUE (conversation_id, ordinal)
);

CREATE INDEX idx_copilot_messages_conversation_ordinal
    ON copilot_messages (conversation_id, ordinal);

CREATE INDEX idx_copilot_messages_owner_created
    ON copilot_messages (owner_id, created_at DESC);
