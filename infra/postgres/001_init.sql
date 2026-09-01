CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id text PRIMARY KEY,
    source text NOT NULL,
    version text NOT NULL,
    service text NOT NULL,
    environment text,
    trust_level text NOT NULL CHECK (trust_level IN ('official', 'reviewed', 'unverified')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, version, service, environment)
);

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
    arguments jsonb NOT NULL,
    result_ref text,
    status text NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'EXECUTED', 'REJECTED', 'FAILED')),
    approved_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    executed_at timestamptz
);

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
