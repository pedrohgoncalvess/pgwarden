# Standalone SQLite storage

PostgreSQL is the default collector storage backend. To opt in to local storage,
set these environment variables only for the standalone collector and its
migrations process:

```dotenv
COLLECTOR_STORAGE_BACKEND=sqlite
COLLECTOR_SQLITE_PATH=/var/lib/pgwarden/collector.sqlite3
ENCRYPTION_KEY=replace-with-a-generated-fernet-key
```

`COLLECTOR_SQLITE_PATH` must identify a persistent file; in-memory storage is
rejected. Generate the encryption key as described in the root README and retain
it across restarts, since target credentials are encrypted with it. `DB_*` is not
used for SQLite storage. Monitored PostgreSQL credentials come from `config.yaml`.

SQLite stores the collector's target registry, metadata and schema history,
metrics, scheduling configuration, commands, execution logs, and heartbeat.
Tables use prefixes such as `metadata_table` and `metric_cpu` because SQLite
does not provide PostgreSQL schemas. JSON arrays/objects use JSON text and
timestamps use UTC ISO 8601 text. SQLite writes use WAL, foreign keys, and full
synchronous durability; transactions roll back on errors or cancellation.

## Manual Docker deployment

From the repository root:

```bash
cp docker/.env.collector.example .env.sqlite
cp collector/config.sqlite.example.yaml config.sqlite.yaml
```

Set a real `ENCRYPTION_KEY`, `SENDER_URL` (the full ingestion endpoint URL), and
`SENDER_PROJECT_KEY` in `.env.sqlite`. Create the project/key on the central
server first. Edit the PostgreSQL targets in `config.sqlite.yaml`. The Compose
file sets the SQLite backend and file path; its named volume persists the
database, source identity, outbox, and rotated credential across restarts.

```bash
docker compose --env-file .env.sqlite -p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml up -d --build
docker compose --env-file .env.sqlite -p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml logs -f collector sender
```

This is a separate deployment; do not combine this file with the central Compose
file using multiple `-f` arguments. It starts migrations, sender initialization,
the collector, and the outgoing HTTP sender. No inbound HTTP port is needed.
The migrations container applies the independent `migrations/sqlite` migration
chain through Yoyo before the collector starts. API, frontend, analytics, and
notifier continue using the central PostgreSQL deployment. Alternatively, use
`bash scripts/start-collector.sh --configure-only`, edit the generated files,
then run `bash scripts/start-collector.sh` from the repository root.

## HTTP sender

`sender-init` installs SQLite triggers and backfills existing ingestible rows
before the collector starts. Each committed metadata change or metric insertion
captures an immutable event in `sender_outbox` in the same transaction. Rollbacks
also roll back the event. Server connection credentials are excluded. Bootstrap
snapshots send parents first, with two passes for column foreign-key references.
Index-column deletions are captured; other entities use soft deletion.

The sender posts ordered batches of at most 500 events and 2 MiB, retries failures
with a bounded backoff, and retains the original IDs and snapshots until a full
acknowledgement. A batch with invalid data stays queued for investigation. Logs
exclude payloads and credentials. One sender process owns each SQLite file.
`SENDER_INTERVAL`, `SENDER_BATCH_SIZE`, and `SENDER_TIMEOUT` configure delivery.

Automatic rotation persists the replacement project key encrypted with
`ENCRYPTION_KEY` in the same SQLite transaction that removes acknowledged events.
After initialization the persisted key takes precedence over `.env.sqlite`, so
restarts cannot restore a stale key. To recover from a revoked or expired key,
update `SENDER_PROJECT_KEY` in `.env.sqlite`, stop the sender, and explicitly set
the replacement before restarting it:

```bash
docker compose --env-file .env.sqlite -p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml stop sender
docker compose --env-file .env.sqlite -p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml run --rm --no-deps sender python sender.py --set-key
docker compose --env-file .env.sqlite -p pgwarden-local -f docker/docker-compose.collector-sqlite.yaml up -d sender
```

Use a fresh volume when moving to a different ingestion project. The source ID
and destination are bound to the local database; restoring a backup must retain
the SQLite state and encryption key together. Stop collector and sender before
applying schema upgrades, then rerun the deployment command.

## Manual native deployment

Install each project's dependencies with `uv sync` in `migrations/` and
`collector/`. Export the SQLite variables above into the shell used for both
commands. Use an absolute database path so both processes open the same file:

```bash
cd migrations
uv run python apply_migrations.py
cd ../collector
# Place the manually configured target file at ./config.yaml.
# Export SENDER_URL and SENDER_PROJECT_KEY, then initialize capture first.
uv run python sender.py --init-only
uv run python main.py
# Run in a second shell with the same environment (Linux/macOS):
# uv run python sender.py
```

The migration runner selects PostgreSQL migrations when the backend is unset or
`postgresql`, and SQLite migrations only when it is `sqlite`. SQLite setup creates
the parent directory; the collector requires an already migrated file and never
falls back to PostgreSQL or creates an empty database silently. Apply migrations
with the collector stopped when upgrading. The provided native commands use
environment variables; the migrations runner does not load a `.env` file.

For manual rollback using Yoyo's CLI, select `migrations/sqlite` as the source and
a `sqlite:///...` database URL for the same file. Every migration has a rollback.
Rolling back removes local data, so back up the file first.

## Deployment limits

Run one collector per SQLite file. System metrics read the machine/container in
which the collector executes; enable them only when that represents the intended
target. The sample disables them for remote PostgreSQL targets. Restart the
collector after adding targets so their collection loops are started.

The included sender delivers events to `POST /v1/ingestion/events`, making them
available to the central API and frontend. Acknowledged events are removed from
the outbox; collected rows remain in SQLite. There is no automatic retention of
local metrics yet, so monitor disk usage, particularly during extended network
outages. See the root README's project ingestion contract. SQLite remains local
collector storage rather than a transparent replica of TimescaleDB.

# Python Environment Setup with Makefile

This repository contains a Makefile to facilitate Python virtual environment setup and management across multiple platforms (Windows and Unix-like systems).

### Method 1: Using Makefile

## Prerequisites

- Python (recommended version: 3.11.0)
- Make (optional)
- Operating System: Windows or Linux/MacOS

## Virtual Environment Setup Methods

### Method 1: Using Makefile (Cross-Platform)

## Prerequisites

- Python (recommended version: 3.11.0)
- Make
- Operating System: Windows or Linux/MacOS

## Environment Setup

### Main Commands

| Command | Description |
|---------|-----------|
| `make setup` | Checks Python installation, creates virtual environment, and installs dependencies |
| `make run` | Executes the main script (`main.py`) after setting up the environment |
| `make clean` | Removes the virtual environment |

### Makefile Details

#### Key Variables
- `PYTHON_VERSION`: Defines Python version (3.11.0)
- `VENV`: Virtual environment directory (`.venv`)

#### Features

1. **Python Installation Check**
   - On Windows: Automatically downloads and installs if not found
   - On Unix-like systems: Provides manual installation instructions

2. **Virtual Environment Creation**
   - Creates an isolated virtual environment
   - Updates pip
   - Supports Windows and Unix systems

3. **Dependency Installation**
   - Uses `requirements.txt` to install packages

### Installation and Usage

#### First-Time Setup

1. Clone the repository
2. Install Python (3.11.0 recommended)
3. Run `make setup`

#### Running the Project

- To setup and run: `make run`
- To clean the environment: `make clean`

### Additional Requirements

- Create a `requirements.txt` file with your dependencies
- Have a main `main.py` script

### Notes

- Windows requires administrator permissions for installation
- On Unix systems, use package managers to install Python

---

### Method 2: Standard Virtual Environment Setup

#### Using `venv` (Recommended)

1. **Create Virtual Environment**
```bash
# On Windows
python -m venv .venv

# On macOS/Linux
python3 -m venv .venv
```

2. **Activate Virtual Environment**
```bash
# Windows (Command Prompt)
.venv\Scripts\activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate
```

3. **Install Dependencies**
```bash
# With virtual environment activated
pip install -r requirements.default.txt
```

4. **Deactivate Virtual Environment**
```bash
deactivate
```

## Project Structure

```
project-root/
│
├── .venv/               # Virtual environment directory
├── src/                 # Source code directory
│   └── main.py          # Main application script
├── tests/               # Test files directory
├── requirements.txt     # Project dependencies
├── README.md            # Project documentation
└── .gitignore           # Git ignore file
```

## Contributing Guidelines

### Getting Started

1. **Fork the Repository**
   - Click "Fork" on the top right of the GitHub repository
   - Clone your forked repository
   ```bash
   git clone https://github.com/YOUR-USERNAME/repository-name.git
   cd repository-name
   ```

2. **Setup Development Environment**
   ```bash
   # Create and activate virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Unix
   .venv\Scripts\activate     # On Windows

   # Install dependencies
   pip install -r requirements.default.txt
   
   # Install development dependencies
   pip install -r requirements-dev.txt  # If you have a separate dev requirements file
   ```

### Contribution Workflow

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write clean, documented code
   - Follow project's coding standards
   - Add/update tests for new functionality

3. **Run Tests**
   ```bash
   # Run all tests
   pytest tests/

   # Run linters (if configured)
   flake8 src/
   ```

4. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: Describe your changes clearly and concisely"
   ```

5. **Push to Your Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request**
   - Open a Pull Request from your fork to the main repository
   - Describe changes in the PR description
   - Link any related issues

### Best Practices

- Write clear, concise commit messages
- Keep pull requests focused and small
- Add tests for new functionality
- Update documentation as needed
- Follow PEP 8 style guidelines
- Use type hints and docstrings

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Collaborate openly and kindly

## License

[Specify your project's license, e.g., MIT, Apache 2.0]

---

### Recommended Tools

- **Virtual Environment**: `venv`
- **Dependency Management**: `pip`
- **Testing**: `pytest`
- **Linting**: `flake8`, `pylint`
- **Type Checking**: `mypy`

## Support

If you encounter any issues or have questions, please [open an issue](link-to-issues) on GitHub.
