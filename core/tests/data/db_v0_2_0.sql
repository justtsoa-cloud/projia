BEGIN TRANSACTION;
CREATE TABLE catalog_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    model_id TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    seen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    summary TEXT,
    summary_upto INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0
, pinned INTEGER NOT NULL DEFAULT 0);
INSERT INTO "conversations" VALUES('277a20b2fff54c81852f7a1ebe3f3abc','Ancienne discussion',1791698450.965723,1791698450.9661524,NULL,0,0,0);
CREATE TABLE kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO "kv" VALUES('schema_version','1');
CREATE TABLE media_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    prompt TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    result_path TEXT,
    error TEXT,
    conversation_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'fact',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0,
    last_used REAL NOT NULL DEFAULT 0,
    source TEXT
);
CREATE TABLE messages (
    uid TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    body TEXT NOT NULL,
    model TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
INSERT INTO "messages" VALUES('d2dd8940a6654f3e982d443845af66b3','277a20b2fff54c81852f7a1ebe3f3abc',1,'user','{"role": "user", "content": "Bonjour depuis 0.2.0"}',NULL,1791698450.9659069,1791698450.9659069);
INSERT INTO "messages" VALUES('e971c6ce2c4e446c8e2ab9eb8c5fdb4f','277a20b2fff54c81852f7a1ebe3f3abc',2,'assistant','{"role": "assistant", "content": "Salut !"}','fake:chatty',1791698450.9661524,1791698450.9661524);
CREATE TABLE preferences (
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    model TEXT NOT NULL,
    strict INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, scope_key)
);
CREATE TABLE quota_state (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE reliability (
    key TEXT PRIMARY KEY,
    ok REAL NOT NULL,
    total REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    conversation_id TEXT
);
CREATE INDEX idx_conv_updated ON conversations(updated_at DESC);
CREATE INDEX idx_msg_conv ON messages(conversation_id, seq);
CREATE INDEX idx_msg_updated ON messages(updated_at);
CREATE INDEX idx_changes_ts ON catalog_changes(ts DESC);
CREATE INDEX idx_spend_ts ON spend(ts);
CREATE INDEX idx_jobs_created ON media_jobs(created_at DESC);
DELETE FROM "sqlite_sequence";
COMMIT;