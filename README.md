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
| **Analytics** | Produces derived performance and database insights. |
| **Notifier** | Evaluates alert rules and sends notifications to configured channels. |
| **TimescaleDB** | Stores PGWarden configuration, metadata, and time-series observations. |
| **Migrations** | Applies the central database schema during startup. |

## Quick start

### Prerequisites

- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/) v2
- Network access from the collector to each PostgreSQL instance you intend to monitor

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

## Contributing

Contributions, bug reports, and feature proposals are welcome.

1. Fork the repository and create a branch from the default branch.
2. Make a focused change and add or update tests where appropriate.
3. Run the relevant checks locally.
4. Open a pull request that explains the problem, approach, and validation.

Please keep pull requests small and avoid committing secrets, generated local files, or production data.

## License

PGWarden is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may use, run, modify, and share it for non-commercial purposes. Commercial use, including monetizing the software or a service based on it, requires separate permission from the copyright holder.
