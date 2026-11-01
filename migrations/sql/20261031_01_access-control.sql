-- depends: 20261030_01_ingestion-projects 20260408_01_vVWWG-api-migrations

CREATE TABLE base.role (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    permissions JSONB NOT NULL DEFAULT '[]',
    project_ids UUID[] NOT NULL DEFAULT '{}',
    server_ids UUID[] NOT NULL DEFAULT '{}',
    database_ids UUID[] NOT NULL DEFAULT '{}'
);
ALTER TABLE base."user" ADD COLUMN role_id BIGINT REFERENCES base.role(id) ON DELETE RESTRICT;
CREATE INDEX user_role_id ON base."user"(role_id);
