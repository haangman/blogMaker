-- blogMaker SQLite 스키마
-- 발행 이력, 소스 헬스, 글 생성 시도 기록, LLM 호출 비용 관측

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS published (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_simhash     INTEGER NOT NULL,
    cluster_embedding   BLOB,
    title               TEXT NOT NULL,
    category            TEXT,
    post_path           TEXT NOT NULL,
    published_at        TEXT NOT NULL,
    source_urls         TEXT
);

CREATE INDEX IF NOT EXISTS idx_pub_at      ON published(published_at);
CREATE INDEX IF NOT EXISTS idx_pub_simhash ON published(cluster_simhash);

CREATE TABLE IF NOT EXISTS source_health (
    source_id        TEXT PRIMARY KEY,
    consec_failures  INTEGER NOT NULL DEFAULT 0,
    last_success_at  TEXT,
    last_error       TEXT,
    disabled         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS article_attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_simhash   INTEGER,
    attempt_num       INTEGER NOT NULL,
    gate_score        REAL,
    gate_failures     TEXT,
    outcome           TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_simhash ON article_attempts(cluster_simhash);

CREATE TABLE IF NOT EXISTS llm_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    purpose         TEXT NOT NULL,
    model           TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cached_tokens   INTEGER,
    cost_usd        REAL,
    duration_ms     INTEGER,
    success         INTEGER NOT NULL,
    error           TEXT,
    at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_at ON llm_calls(at);
