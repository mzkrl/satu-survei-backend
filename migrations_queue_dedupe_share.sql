-- ==========================================
-- SATUSURVEY: QUEUE, DEDUPE, SHARE MIGRATION
-- Idempotent; safe to run on existing databases.
-- ==========================================

-- 1. PDF content hash for dedupe
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_documents_file_hash
    ON documents(file_hash);

-- 2. Public share links
ALTER TABLE analyses
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(64);

ALTER TABLE analyses
    ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_analyses_share_token
    ON analyses(share_token)
    WHERE share_token IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analyses_user_status
    ON analyses(user_id, status);

-- Allow the new queued state. Drop the old check first because PostgreSQL
-- cannot widen an existing CHECK constraint in place.
ALTER TABLE analyses DROP CONSTRAINT IF EXISTS analyses_status_check;
ALTER TABLE analyses ADD CONSTRAINT analyses_status_check
    CHECK (status IN ('draft', 'queued', 'processing', 'completed', 'failed'));

-- 3. PostgreSQL-backed analysis queue (no Redis required)
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY,

    analysis_id UUID NOT NULL
        REFERENCES analyses(id) ON DELETE CASCADE,

    document_id UUID NOT NULL
        REFERENCES documents(id) ON DELETE CASCADE,

    user_id UUID NOT NULL,

    file_hash VARCHAR(64) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),

    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),

    max_attempts INTEGER NOT NULL DEFAULT 2
        CHECK (max_attempts >= 1),

    last_error TEXT,

    worker_id VARCHAR(100),

    run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    locked_until TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    finished_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_jobs_analysis
    ON analysis_jobs(analysis_id);

-- At most one queued/running job per user + identical PDF.
CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_jobs_active_user_hash
    ON analysis_jobs(user_id, file_hash)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_claim
    ON analysis_jobs(status, run_after, created_at);