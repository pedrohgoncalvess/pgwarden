-- api migrations
-- depends: 20260324_01_pUn2z

CREATE SCHEMA "base";

CREATE TABLE "base"."user" (
    id SERIAL,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    inserted_at TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at TIMESTAMP,

    CONSTRAINT user_pk PRIMARY KEY (id)
);

COMMENT ON TABLE "base"."user" IS 'Standard USERS table for the application, storing identity and authentication details.';
COMMENT ON COLUMN "base"."user".password IS 'Hashed password string.';
COMMENT ON COLUMN "base"."user".is_admin IS 'Flag to identify administrators with elevated privileges.';

CREATE TABLE "base"."refresh" (
    id SERIAL,
    user_id INTEGER NOT NULL,
    token UUID NOT NULL UNIQUE,
    used BOOLEAN DEFAULT FALSE,
    inserted_at TIMESTAMP NOT NULL,

    CONSTRAINT refresh_pk PRIMARY KEY (id)
);

COMMENT ON TABLE "base"."refresh" IS 'Stores refresh tokens for extended user sessions (JWT refresh cycle).';
COMMENT ON COLUMN "base"."refresh".token IS 'Unique UUID token for session refresh.';
COMMENT ON COLUMN "base"."refresh".used IS 'Tracks if the token has already been consumed to prevent reuse attacks.';