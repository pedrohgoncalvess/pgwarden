<div align="center">
  <img src="frontend/static/branding/logo.jpg" alt="PGWarden logo" width="180" />
  <h1>PGWarden</h1>
  <p><strong>Source-available PostgreSQL observability, schema intelligence, and alerting.</strong></p>
  <p>Monitor your PostgreSQL fleet from one place, investigate performance issues, and keep schema changes visible.</p>
</div>

![PGWarden overview](docs/images/overview.png)

## Why PGWarden?

Running PostgreSQL well means seeing more than whether a database is online. PGWarden brings operational signals, query activity, lock contention, schema metadata, and alerting into one self-hosted workspace so teams can identify problems faster and track how their databases evolve.

## Highlights

- **Monitor multiple PostgreSQL servers** from a centralized dashboard.
- **Inspect live workload** with active-query and lock visibility.
- **Track database health** through connections, CPU, memory, throughput, table statistics, vacuum signals, and index usage.
- **Explore schema metadata and history** for tables, columns, indexes, and related database objects.
- **Analyze performance trends** using time-series data stored in TimescaleDB.
- **Configure alerts** for important operational thresholds, with Slack, Discord, Microsoft Teams, and SMTP email delivery.
- **Protect credentials** by encrypting stored database and notification credentials with Fernet encryption.

## Architecture at a glance

PGWarden is a Docker Compose stack with focused services. The API and web interface provide the operator experience; background workers collect data, calculate analytics, and deliver notifications; TimescaleDB stores application data and time-series metrics.

| Component | Responsibility |
| --- | --- |
| **Frontend** | Web dashboard for monitoring, schema exploration, configuration, and alerts. |
| **API** | FastAPI service for authentication, configuration, and data access. |
| **Collector** | Polls registered PostgreSQL targets and persists operational metrics. |
| **Sender** | Forwards the remote collector's durable SQLite outbox to the HTTP API. |
| **Analytics** | Produces derived performance and database insights. |
| **Notifier** | Evaluates alert rules and sends notifications to configured channels. |
| **TimescaleDB** | Stores PGWarden configuration, metadata, and time-series observations. |
| **Migrations** | Applies the central database schema during startup. |

## Quick start

### Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/) v2
- Network access from the collector to each PostgreSQL instance you intend to monitor

### Installation scripts

Use one installer with a deployment mode. The three `start-*.sh` scripts are
shortcuts to the same implementation, so clone, configuration, and startup logic
stay consistent. Run these commands in Bash on Linux, macOS, or WSL with Docker
access. Docker and Git must already be installed.

To bootstrap a machine before cloning, download the installer, inspect it, and
run the desired mode. For a release deployment, replace `main` in the download
URL with a release tag and pass the same tag through `--ref`.

```bash
curl -fsSLo pgwarden-install.sh https://raw.githubusercontent.com/pedrohgoncalvess/pgwarden/main/scripts/install.sh
less pgwarden-install.sh

# Complete installation: clones the repository, generates secrets and starts it.
bash pgwarden-install.sh full --dir "$HOME/pgwarden"

# Central receiver and dashboard, on the receiving machine.
bash pgwarden-install.sh server --dir "$HOME/pgwarden"

# Remote collector and HTTP sender, on the monitored network.
bash pgwarden-install.sh collector --dir "$HOME/pgwarden" --configure-only
# Edit $HOME/pgwarden/.env.sqlite and $HOME/pgwarden/config.sqlite.yaml.
bash pgwarden-install.sh collector --dir "$HOME/pgwarden"
```

Choose `full` or `server` for a central installation; they are alternatives.
For remote collection, start `server` first, sign in using the generated `.env`
administrator credentials, create a project in **Settings → Projects**, and copy
its ingestion key into the collector's `.env.sqlite`. Set `SENDER_URL` to the full
receiving URL, such as `https://warden.example.com/v1/ingestion/events`, and
configure the PostgreSQL targets in `config.sqlite.yaml`. Then start `collector`.
The sender makes outgoing requests; it does not expose an HTTP port.

From an existing checkout, equivalent shortcuts are:

```bash
bash scripts/start-full.sh
bash scripts/start-server.sh
bash scripts/start-collector.sh --configure-only
bash scripts/start-collector.sh
# Or: bash scripts/install.sh <full|server|collector> [options]
```

The installer reuses its checkout, or clones into `--dir` when it does not exist,
then changes to that directory before running Docker Compose. It preserves
existing configuration and never runs `git pull` or switches branches implicitly.
Use `--ref <branch-or-tag>` for a new clone, `--repo <url>` for a fork, and
`--name <compose-project-name>` to override the project name. `--configure-only`
creates missing files without starting application services; secret generation
uses a temporary Python Docker container, so local Python is not required.

On first installation, `full` and `server` generate `.env` with random encryption,
JWT, database, and administrator secrets. `full` also creates `config.local.yaml`
with matching database credentials. Existing `.env` files remain untouched;
review the selected collector config yourself when reusing an existing setup.
The collector generates `.env.sqlite` and `config.sqlite.yaml`, and requires the
destination and monitored targets to be configured before startup. Keep these
files and the Docker volumes across restarts, especially `ENCRYPTION_KEY`.

Only the full-stack Compose remains at the repository root. Alternate deployments
and the test Compose are in `docker/`; their build and mount paths are relative
to that directory. Always keep the deployment's Compose project name when running
manual commands, so it continues using the same named volumes.

### 1. Clone the repository

```bash
git clone https://github.com/pedrohgoncalvess/pgwarden.git
cd pgwarden
```

### 2. Create and configure your environment file

```bash
cp .env.example .env
```

Before starting the stack, replace the placeholder values in `.env`. At a minimum, generate unique values for `ENCRYPTION_KEY` and `JWT_SECRET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the first value for `ENCRYPTION_KEY` and the second for `JWT_SECRET_KEY`. Do not reuse the example values or commit your `.env` file. Review the optional database, API port, and CORS settings in [`.env.example`](.env.example) for your environment.

### 3. Start PGWarden

```bash
docker compose up -d --build
```

The migrations service completes before the application services start. Check the stack status with:

```bash
docker compose ps
```

Docker builds use BuildKit caches for Python and npm downloads. Dependency layers
are reused when only source files change, and production images exclude Python
development dependencies and build tools. Analytics and notifier use dedicated
Dockerfile ignore files to send only their source and workspace manifests.

To rebuild all application images without starting containers:

```bash
docker compose build
```

Keep the build cache between builds; use `--no-cache` only when troubleshooting.
For local Python development and tests, `uv sync` still installs the default
`dev` group. The frontend installs dependencies once and prunes development
packages in a separate stage before assembling the runtime image.

### 4. Open the application

- **Dashboard:** [http://localhost:3000](http://localhost:3000)
- **API documentation:** [http://localhost:8080/docs](http://localhost:8080/docs)

For a production deployment, set distinct database and administrator credentials rather than relying on Compose defaults. PGWarden warns when shipped default credentials remain active.

## Configuration and operations

The root [`config.yaml`](config.yaml) contains collector and notifier configuration. All environment variables are documented in [`.env.example`](.env.example). For production, inject the equivalent values through Docker secrets or your deployment platform's secret manager instead of committing a `.env` file.

Useful Compose commands:

```bash
# Follow all service logs
docker compose logs -f

# Stop the stack while keeping the database volume
docker compose down
```

### Central server receiving data over HTTP (without a collector)

Configure `.env` as described in the quick start, then start the receiving stack:

```bash
docker compose -p pgwarden -f docker/docker-compose.server.yaml up -d --build
```

This standalone Compose file starts TimescaleDB, migrations, API, frontend,
analytics, and notifier. It does not start a collector. Use it as an alternative
to `docker-compose.yaml`, without combining the two files. The database is stored
in the `pgwarden_data` volume and is reachable only inside the Docker network;
services always connect to `db:5432`, regardless of `DB_HOST` or `DB_PORT` in `.env`.
Central migrations always use PostgreSQL, even if `.env` selects SQLite for a
separate collector. Notifier still reads the `notifier` section of `config.yaml`,
and analytics reads `analytics/config.yaml`.

Open the dashboard at `http://localhost:3000` (or the configured `FRONTEND_PORT`),
sign in with `PGWARDEN_EMAIL` and `PGWARDEN_PASSWORD`, then create a project in
**Settings → Projects** and save its ingestion key. Configure the external sender
to POST batches to `http://<server>:8080/v1/ingestion/events` (or `API_PORT`)
with `Authorization: Bearer <project-key>`. Put HTTPS in front of the API when
exposing it remotely. The payload and acknowledgement contract are documented
in [Projects and remote event ingestion](#projects-and-remote-event-ingestion).
The remote collector deployment in `docker/docker-compose.collector-sqlite.yaml`
includes the HTTP sender and forwards committed SQLite snapshots automatically.

Use the same file for subsequent operations:

```bash
docker compose -p pgwarden -f docker/docker-compose.server.yaml logs -f
docker compose -p pgwarden -f docker/docker-compose.server.yaml down
```

### Standalone collector with SQLite (manual opt-in)

The default stack continues to use PostgreSQL/TimescaleDB for every service.
A separately deployed collector can instead persist its configuration, metadata,
metrics, execution history, and heartbeat in SQLite without reaching the central
database. Connections to monitored databases still use PostgreSQL.

See [the collector SQLite setup](collector/README.MD#standalone-sqlite-storage)
for the optional Compose file and native setup. SQLite has its own Yoyo migrations.
The remote Compose starts an outgoing HTTP sender with a durable SQLite outbox;
the central API provides the receiving endpoint described below.

### Projects and remote event ingestion

Apply the PostgreSQL Yoyo migrations before upgrading the API and collector.
Administrators can open **Settings → Projects** to create a project and obtain
its initial key, change its policies, rotate keys, or revoke them. Keys permit
ingestion only; administration continues to require an administrator JWT.

Expiration and automatic rotation are independently optional. `key_expiration_days`
sets a new key's lifetime; omitting it produces a non-expiring key.
`rotation_interval_days` enables automatic replacement, checked approximately once
per minute by API workers using PostgreSQL row locks. Leave it empty for manual
rotation. If both policies are set, rotation must precede expiration. Updating a
lifetime policy affects newly issued keys, not a key already in use.

Automatic rotation uses `rotation_grace_hours` (default 24, maximum 168). During
that overlap, an accepted old key receives `replacement_key` in successful
ingestion responses, including retry responses. The sender **must persist that
replacement credential atomically before acknowledging/deleting local records**.
After overlap or expiration, the old key receives 401; an administrator must issue
a fresh key if an offline sender missed the handoff. Revoking the current key
stops scheduled rotation until an administrator issues another key. A manual
rotation defaults to zero overlap and immediately revokes every previous key.

Only key hashes and prefixes are exposed through key-list responses. Automatic
handoff temporarily retains the successor encrypted with `ENCRYPTION_KEY` so a
lost response can be retried. The rotation worker removes this encrypted copy
after no previous key remains eligible for handoff. Protect and retain that
server encryption key. Use HTTPS and keep credentials in the Authorization
header, never in a URL or event payload.

The standalone sender should call the main API:

```http
POST /v1/ingestion/events
Authorization: Bearer pgw_your_project_key
Content-Type: application/json
```

The frontend also proxies `/api/v1/ingestion/events`; configure proxy body limits
when using it. The API accepts at most 500 events and 2 MiB per request:

```json
{
  "version": 1,
  "source_id": "31d47764-9a83-4a8a-8fe6-220ef3046092",
  "events": [
    {
      "event_id": "72cd642a-a0d3-439c-8fba-b42a25ab6a6f",
      "occurred_at": "2026-10-30T12:00:00Z",
      "table": "collector_server",
      "local_id": 1,
      "data": { "name": "production-postgres" }
    },
    {
      "event_id": "9f15e455-2fa5-48c8-98ac-f730c2670054",
      "occurred_at": "2026-10-30T12:00:01Z",
      "table": "metric_cpu",
      "data": {
        "server_id": 1,
        "collected_at": "2026-10-30T12:00:01Z",
        "cpu_percent": 42.5,
        "cpu_count": 4
      }
    }
  ]
}
```

Persist a stable `source_id` for each SQLite installation. Persist each event UUID
and its immutable snapshot before sending; use the same content and ID on retry.
A new snapshot needs a new event ID. The authenticated key determines the project;
clients cannot supply a central project or entity ID. All row references use
SQLite local IDs, mapped by `(project, source, table, local_id)` on the server.

Send parent entities before dependent rows, including across batches:
`collector_server`, `metadata_database`, `metadata_table`, `metadata_column`,
`metadata_index`, then `metadata_index_column` and the relevant `metric_*` rows.
All eleven collector metric tables are accepted. An entity event needs `local_id`;
metrics and index-column relationships do not. Use timezone-aware ISO timestamps.
`occurred_at` orders entity snapshots, so older snapshots cannot overwrite newer
ones. Keep index-column relationship changes in chronological order.

`data` contains destination row fields, excluding `id`, `public_id`, actor IDs,
and ingestion-internal fields. A server accepts only `name`, `last_seen_at`,
`last_error`, `created_at`, `updated_at`, and `deleted_at`: **never send database
connection credentials**. Other entity and metric fields follow the collector's
table columns. Control tables, local run logs, and local schema-history tables
are not ingestible. Central metadata changes generate central schema history.
Soft deletion uses `deleted_at`; physical `operation: "delete"` is supported only
for index-column relationships, with its index/column IDs and ordinal position.

The API writes the event receipt, ID mappings, metadata, and metrics in one
transaction. A successful response includes `accepted`, `duplicates`,
`acknowledged_event_ids`, and an optional `replacement_key`. Remove only acknowledged
local events. Missing parents or an event ID reused with different content return
409; invalid rows return 422; oversized batches return 413. These failures roll
back the entire batch, so retain it and correct/retry delivery. Keep receipt data
while senders may retry; no automatic receipt retention is enabled yet.

Imported servers are marked as remotely collected so the central PostgreSQL
collector does not poll them or record the central host's system metrics against
them. Their normalized metrics are available through the existing API and UI.

Run the dedicated backend integration tests against a disposable PostgreSQL
connection by setting `INGESTION_TEST_DATABASE_URL` and running
`pytest tests/test_ingestion.py` from `api/`. They create their own database and
verify migration application/rollback, actual metric writes, isolation,
deduplication, and key lifecycles. The test baseline omits Timescale-specific DDL;
the production stack still requires TimescaleDB.

## Users, roles, and resource access

Apply `20261031_01_access-control` with the PostgreSQL migrations before starting
the updated API. Administrators manage accounts in **Settings → Users** and
roles in **Settings → Roles**. Each non-administrator must have one role; existing non-administrator
accounts without a role have no resource access until assigned. Administrators
always have access to every project, server, and database.

Creating an account in the interface generates an eight-character password with
letters, numbers, and symbols. The initial credential is shown once to the
administrator after creation. Every signed-in user can open **Settings → Change
password**, enter the current password, and confirm a new password of at least
eight characters. Passwords are hashed before storage.

Roles explicitly select projects, servers, and databases. Selecting a project
does not automatically grant every server or database beneath it. A server with
a project requires that project's grant, and a database requires its server's
grant. Local servers without a project can be granted directly. Removing a
parent grant also blocks stale child grants. Catalogs, search, tags, alerts,
scheduler controls, and live streams enforce these boundaries in the API.

Each role has six independent capabilities: `alerts.read`, `alerts.configure`,
`documentation.read`, `documentation.configure`, `schedulers.read`, and
`schedulers.configure`. Enable both read and configure for a feature when its
users should manage it through the interface. User and role management, project
keys, and connection provisioning remain administrator-only. Removing an account
blocks login and existing tokens; the last active administrator cannot be removed.

Run the access-control integration suite with `INGESTION_TEST_DATABASE_URL` set
to a disposable PostgreSQL administrative connection and run
`pytest tests/test_access_control.py` from `api/`. The tests create and remove
their own database, including migration rollback validation.

## CI and releases

Pull requests and pushes to `main` validate all services and build every Docker
image. Version tags trigger validated image publication to GHCR and a GitHub
release. See [CI and release instructions](.github/README.md) for supported tags,
image names and repository configuration.

## Contributing

Contributions, bug reports, and feature proposals are welcome.

1. Fork the repository and create a branch from the default branch.
2. Make a focused change and add or update tests where appropriate.
3. Run the relevant checks locally.
4. Open a pull request that explains the problem, approach, and validation.

Please keep pull requests small and avoid committing secrets, generated local files, or production data.

## License

PGWarden is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may use, run, modify, and share it for non-commercial purposes. Commercial use, including monetizing the software or a service based on it, requires separate permission from the copyright holder.
