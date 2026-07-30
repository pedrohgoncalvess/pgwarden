-- depends: 20260720_01_notifier-module
CREATE TABLE "base"."service_heartbeat" (
    service TEXT PRIMARY KEY,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "service_heartbeat_service_ck"
        CHECK (service IN ('collector', 'analytics', 'notifier'))
);
