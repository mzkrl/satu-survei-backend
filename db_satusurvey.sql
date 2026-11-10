-- ==========================================
-- SATUSURVEY MVP DATABASE
-- PostgreSQL
-- ==========================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username VARCHAR(255) UNIQUE NOT NULL,
  email VARCHAR(255) UNIQUE,
  password VARCHAR(255) NOT NULL
);

-- 1. ANALYSIS
-- ==========================================

CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    title VARCHAR(255) NOT NULL,

    status VARCHAR(30) NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft',
            'processing',
            'completed',
            'failed'
        )),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 2. DOCUMENT
-- ==========================================

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    analysis_id UUID NOT NULL
        REFERENCES analyses(id) ON DELETE CASCADE,

    file VARCHAR(500) NOT NULL,

    filename VARCHAR(255) NOT NULL,

    title VARCHAR(500),

    publisher VARCHAR(255),

    publication_date DATE,

    source_url TEXT,

    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'processing',
            'completed',
            'failed'
        )),

    extracted_text TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 3. EVIDENCE
-- ==========================================

CREATE TABLE evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_id UUID NOT NULL
        REFERENCES documents(id) ON DELETE CASCADE,

    metric VARCHAR(255) NOT NULL,

    value NUMERIC(20, 6) NOT NULL,

    unit VARCHAR(100),

    population TEXT,

    geography VARCHAR(255),

    period VARCHAR(100),

    sample_size INTEGER
        CHECK (sample_size IS NULL OR sample_size >= 0),

    raw_excerpt TEXT,

    page_number INTEGER
        CHECK (page_number IS NULL OR page_number > 0),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 4. CLAIM
-- ==========================================

CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    analysis_id UUID NOT NULL
        REFERENCES analyses(id) ON DELETE CASCADE,

    document_id UUID NOT NULL
        REFERENCES documents(id) ON DELETE CASCADE,

    statement TEXT NOT NULL,

    category VARCHAR(100),

    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'processing',
            'evaluated',
            'failed'
        )),

    raw_excerpt TEXT,

    page_number INTEGER
        CHECK (page_number IS NULL OR page_number > 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- 5. EVALUATION
-- ==========================================

CREATE TABLE evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    claim_id UUID NOT NULL
        REFERENCES claims(id) ON DELETE CASCADE,

    verdict VARCHAR(30) NOT NULL
        CHECK (verdict IN (
            'valid',
            'questionable',
            'invalid',
            'insufficient_evidence'
        )),

    confidence NUMERIC(5, 4)
        CHECK (
            confidence IS NULL OR
            confidence BETWEEN 0 AND 1
        ),

    explanation TEXT,

    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(evidence_ids) = 'array'),

    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,

    limitations JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(limitations) = 'array'),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ==========================================
-- INDEXES
-- ==========================================

CREATE INDEX idx_analyses_user
    ON analyses(user_id);

CREATE INDEX idx_documents_analysis
    ON documents(analysis_id);

CREATE INDEX idx_evidence_document
    ON evidence(document_id);

CREATE INDEX idx_evidence_metric
    ON evidence(metric);

CREATE INDEX idx_claims_analysis
    ON claims(analysis_id);

CREATE INDEX idx_evaluations_claim
    ON evaluations(claim_id);

CREATE INDEX idx_evaluations_created
    ON evaluations(claim_id, created_at DESC);