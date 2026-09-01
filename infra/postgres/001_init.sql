CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id text PRIMARY KEY,
    source text NOT NULL,
    version text NOT NULL,
    service text NOT NULL,
    environment text,
    trust_level text NOT NULL CHECK (trust_level IN ('official', 'reviewed', 'unverified')),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_source_version_service_environment_key;

CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section text NOT NULL,
    content text NOT NULL,
    embedding vector(768),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX IF NOT EXISTS chunks_search_idx ON chunks USING gin (search_vector);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS documents_scope_idx ON documents (service, environment, trust_level);

CREATE TABLE IF NOT EXISTS incidents (
    id text PRIMARY KEY,
    service text NOT NULL,
    environment text NOT NULL,
    alert text NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('OPEN', 'INVESTIGATING', 'RESOLVED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (window_end > window_start)
);

CREATE TABLE IF NOT EXISTS messages (
    id bigserial PRIMARY KEY,
    incident_id text NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
    content jsonb NOT NULL,
    model_info jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id text PRIMARY KEY,
    incident_id text NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    tool text NOT NULL,
    reason text NOT NULL DEFAULT '',
    arguments jsonb NOT NULL,
    result_ref text,
    status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'EXECUTED', 'REJECTED', 'FAILED')),
    approved_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    executed_at timestamptz
);

ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS reason text NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS evidence (
    id text NOT NULL,
    incident_id text NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    chunk_id text REFERENCES chunks(id),
    tool_call_id text REFERENCES tool_calls(id),
    quote_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (incident_id, id),
    CHECK ((chunk_id IS NOT NULL) <> (tool_call_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS evaluations (
    case_id text NOT NULL,
    config_version text NOT NULL,
    metrics jsonb NOT NULL,
    output jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, config_version)
);

CREATE TABLE IF NOT EXISTS feedback (
    id bigserial PRIMARY KEY,
    incident_id text NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    correctness smallint NOT NULL CHECK (correctness BETWEEN 1 AND 5),
    citation_quality smallint NOT NULL CHECK (citation_quality BETWEEN 1 AND 5),
    helpfulness smallint NOT NULL CHECK (helpfulness BETWEEN 1 AND 5),
    label text NOT NULL,
    correction text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS background_jobs (
    id text PRIMARY KEY,
    queue text NOT NULL,
    kind text NOT NULL,
    status text NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    payload jsonb NOT NULL,
    result jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS traces (
    id text PRIMARY KEY,
    incident_id text REFERENCES incidents(id) ON DELETE SET NULL,
    operation text NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL,
    duration_ms double precision NOT NULL CHECK (duration_ms >= 0),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS traces_incident_started_idx ON traces (incident_id, started_at DESC);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key text PRIMARY KEY,
    provider text NOT NULL,
    model text NOT NULL,
    response jsonb NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
    fallback_used boolean NOT NULL DEFAULT false,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE llm_cache ADD COLUMN IF NOT EXISTS fallback_used boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS llm_cache_expiry_idx ON llm_cache (expires_at);

CREATE TABLE IF NOT EXISTS daily_costs (
    usage_date date PRIMARY KEY,
    cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
    input_tokens bigint NOT NULL DEFAULT 0,
    output_tokens bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
