-- depends: 20260730_01-service-commands

CREATE SCHEMA ingestion;

CREATE TABLE ingestion.project (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    key_expiration_days INTEGER CHECK (key_expiration_days BETWEEN 1 AND 3650),
    rotation_interval_days INTEGER CHECK (rotation_interval_days BETWEEN 1 AND 3650),
    rotation_grace_hours INTEGER NOT NULL DEFAULT 24 CHECK (rotation_grace_hours BETWEEN 0 AND 168),
    next_rotation_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_event_at TIMESTAMPTZ,
    CHECK (rotation_interval_days IS NULL OR rotation_grace_hours > 0),
    CHECK (rotation_interval_days IS NULL OR key_expiration_days IS NULL
           OR rotation_interval_days < key_expiration_days)
);

CREATE TABLE ingestion.api_key (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES ingestion.project(id) ON DELETE CASCADE,
    key_hash CHAR(64) NOT NULL UNIQUE,
    prefix VARCHAR(16) NOT NULL,
    encrypted_secret TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    retire_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ingestion_current_key ON ingestion.api_key(project_id)
    WHERE retire_at IS NULL AND revoked_at IS NULL;
CREATE INDEX ingestion_rotation_due ON ingestion.project(next_rotation_at)
    WHERE enabled AND rotation_interval_days IS NOT NULL;

CREATE TABLE ingestion.entity (
    project_id UUID NOT NULL REFERENCES ingestion.project(id) ON DELETE CASCADE,
    source_id UUID NOT NULL,
    table_name TEXT NOT NULL,
    local_id BIGINT NOT NULL CHECK (local_id > 0),
    central_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (project_id, source_id, table_name, local_id)
);

CREATE TABLE ingestion.event (
    project_id UUID NOT NULL REFERENCES ingestion.project(id) ON DELETE CASCADE,
    source_id UUID NOT NULL,
    event_id UUID NOT NULL,
    table_name TEXT NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, source_id, event_id)
);
CREATE INDEX ingestion_event_received ON ingestion.event(project_id, received_at DESC);

ALTER TABLE collector.server ADD COLUMN ingestion_project_id UUID REFERENCES ingestion.project(id);
