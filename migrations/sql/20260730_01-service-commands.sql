-- depends: 20260729_01_service-heartbeats
CREATE TABLE base.service_command (
    id BIGSERIAL PRIMARY KEY,
    service TEXT NOT NULL CHECK (service IN ('notifier')),
    action TEXT NOT NULL CHECK (action IN ('force_run')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consumed_at TIMESTAMPTZ
);

CREATE INDEX service_command_pending_idx
    ON base.service_command (service, created_at)
    WHERE consumed_at IS NULL;
