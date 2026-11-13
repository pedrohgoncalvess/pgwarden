"""Durable SQLite outbox and outgoing HTTP delivery to the central API."""

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from cryptography.fernet import Fernet


ENTITIES = (
    "collector_server",
    "metadata_database",
    "metadata_table",
    "metadata_column",
    "metadata_index",
    "metadata_index_column",
)
METRICS = (
    "metric_cpu",
    "metric_ram",
    "metric_disk",
    "metric_io",
    "metric_database_stat",
    "metric_table",
    "metric_column",
    "metric_index",
    "metric_session",
    "metric_lock",
    "metric_native_query",
    "metric_query_workload",
)
EXCLUDED = {"id", "public_id", "created_by", "updated_by", "deleted_by"}
SERVER_FIELDS = {
    "name",
    "last_seen_at",
    "last_error",
    "created_at",
    "updated_at",
    "deleted_at",
}
CLOCK = """UPDATE sender_clock SET value = max(value + 1,
    CAST((julianday('now') - 2440587.5) * 86400000000 AS INTEGER));"""
MAX_BYTES = 2 * 1024 * 1024
HEARTBEAT_TABLE = "base_service_heartbeat"


def connect(path: Path) -> sqlite3.Connection:
    """Require an existing migrated database and keep acknowledgements durable."""
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=rw", uri=True, timeout=30
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def capture_sql(
    table: str, columns: list[str], prefix: str = "NEW.", operation: str = "upsert"
) -> str:
    """Build SQL only from our table allowlist and migrated column names."""
    fields = ", ".join(f"'{name}', {prefix}\"{name}\"" for name in columns)
    if table == "metric_query_workload" and "statement_text_id" in columns:
        fields = ", ".join(f"'{name}', {prefix}\"{name}\""
                           for name in columns if name != "statement_text_id")
        reference = f'{prefix}"statement_text_id"'
        fields += f""", 'query', (SELECT query FROM metric_statement_text WHERE id={reference}),
            'query_hash', (SELECT query_hash FROM metric_statement_text WHERE id={reference})"""
    identity = (
        "NULL"
        if table in METRICS or table in ("metadata_index_column", HEARTBEAT_TABLE)
        else f'{prefix}"id"'
    )
    return f"""INSERT INTO sender_outbox(event_id, occurred_us, table_name, local_id, operation, data)
        SELECT lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-'
            || hex(randomblob(2)) || '-' || hex(randomblob(2)) || '-' || hex(randomblob(6))),
        (SELECT value FROM sender_clock),
        '{table}', {identity}, '{operation}', json_object({fields})"""


def install_heartbeat_capture(connection: sqlite3.Connection) -> None:
    """Forward the collector's own clock, including upgrades of existing outboxes."""
    columns = ["service", "updated_at"]
    missing = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
        (f"sender_{HEARTBEAT_TABLE}_update",),
    ).fetchone() is None
    for action in ("INSERT", "UPDATE"):
        trigger = f"sender_{HEARTBEAT_TABLE}_{action.lower()}"
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger}")
        connection.execute(
            f'CREATE TRIGGER {trigger} AFTER {action} ON "{HEARTBEAT_TABLE}" '
            f"WHEN NEW.service = 'collector' "
            f"BEGIN {CLOCK} {capture_sql(HEARTBEAT_TABLE, columns)}; END"
        )
    if missing:
        connection.execute(CLOCK)
        connection.execute(
            capture_sql(HEARTBEAT_TABLE, columns, prefix="")
            + f" FROM {HEARTBEAT_TABLE} WHERE service = 'collector'"
        )


def initialize(
    connection: sqlite3.Connection,
    url: str,
    key: str,
    cipher: Fernet,
    *,
    set_key: bool = False,
) -> None:
    """Install transactional capture before starting collection; backfill once."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "SENDER_URL must be an HTTP(S) endpoint without credentials, query or fragment"
        )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS sender_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), source_id TEXT NOT NULL,
            url TEXT NOT NULL, project_key BLOB NOT NULL)"""
        )
        state = connection.execute("SELECT * FROM sender_state").fetchone()
        if state:
            if state["url"] != url:
                raise ValueError(
                    "SENDER_URL differs from the persisted destination; use a separate SQLite volume"
                )
            if set_key:
                if not key.startswith("pgw_"):
                    raise ValueError(
                        "Set SENDER_PROJECT_KEY to a project ingestion key"
                    )
                connection.execute(
                    "UPDATE sender_state SET project_key=?",
                    (cipher.encrypt(key.encode()),),
                )
            else:
                cipher.decrypt(state["project_key"])
            # Schema upgrades add statement fields. Refresh capture even for an
            # already configured sender; otherwise its old trigger drops them.
            table = "metric_query_workload"
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            connection.execute(f"DROP TRIGGER IF EXISTS sender_{table}_insert")
            connection.execute(
                f'CREATE TRIGGER sender_{table}_insert AFTER INSERT ON "{table}" '
                f'BEGIN {CLOCK} {capture_sql(table, columns)}; END'
            )
            install_heartbeat_capture(connection)
            connection.commit()
            return
        if not key.startswith("pgw_") or "replace" in key:
            raise ValueError("Set SENDER_PROJECT_KEY to a project ingestion key")
        connection.execute(
            "INSERT INTO sender_state VALUES(1, ?, ?, ?)",
            (str(uuid4()), url, cipher.encrypt(key.encode())),
        )
        connection.execute("CREATE TABLE sender_clock(value INTEGER NOT NULL)")
        connection.execute("INSERT INTO sender_clock VALUES(0)")
        connection.execute(
            """CREATE TABLE sender_outbox (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
            occurred_us INTEGER NOT NULL, table_name TEXT NOT NULL, local_id INTEGER,
            operation TEXT NOT NULL, data TEXT NOT NULL)"""
        )
        for table in ENTITIES + METRICS:
            columns = [
                row[1]
                for row in connection.execute(f'PRAGMA table_info("{table}")')
                if row[1] not in EXCLUDED
                and (table != "collector_server" or row[1] in SERVER_FIELDS)
            ]
            if not columns:
                raise ValueError(f"Missing migrated table: {table}")
            actions = ("INSERT",) if table in METRICS else ("INSERT", "UPDATE")
            for action in actions:
                connection.execute(
                    f"""CREATE TRIGGER sender_{table}_{action.lower()}
                    AFTER {action} ON "{table}" BEGIN {CLOCK} {capture_sql(table, columns)}; END"""
                )
            if table == "metadata_index_column":
                connection.execute(
                    f"""CREATE TRIGGER sender_index_column_delete
                    AFTER DELETE ON metadata_index_column BEGIN {CLOCK}
                    {capture_sql(table, columns, 'OLD.', 'delete')}; END"""
                )
            # Bootstrap every parent before metrics. Column FK references get a
            # second pass after all columns have identities, including cycles.
            connection.execute(CLOCK)
            snapshot = capture_sql(table, columns, prefix="")
            if table == "metadata_column":
                snapshot = snapshot.replace('"fk_table_id"', "NULL").replace(
                    '"fk_column_id"', "NULL"
                )
            connection.execute(snapshot + f' FROM "{table}"')
            if table == "metadata_column":
                connection.execute(CLOCK)
                connection.execute(
                    capture_sql(table, columns, prefix="") + f' FROM "{table}"'
                )
        install_heartbeat_capture(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


class NoRedirect(HTTPRedirectHandler):
    """Never forward a project credential to a redirected destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeliveryError(RuntimeError):
    """Expose a safe status message without including response data."""


def post(url: str, key: str, body: bytes, timeout: float) -> dict:
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        # Response bodies may echo event data. Log only the HTTP status.
        raise DeliveryError(f"Ingestion HTTP {error.code}; batch retained") from None


def deliver(
    connection: sqlite3.Connection,
    cipher: Fernet,
    batch_size: int,
    timeout: float,
    transport=post,
) -> int:
    """Send immutable snapshots and atomically persist rotation before removal."""
    state = connection.execute("SELECT * FROM sender_state").fetchone()
    rows = connection.execute(
        "SELECT * FROM sender_outbox ORDER BY seq LIMIT ?", (batch_size,)
    ).fetchall()
    events = []
    body = b""
    for row in rows:
        data = json.loads(row["data"])
        # The registry can contain either plaintext or Fernet database names.
        if row["table_name"] == "metadata_database" and data["db_name"].startswith(
            "gAAAA"
        ):
            data["db_name"] = cipher.decrypt(data["db_name"].encode()).decode()
        item = {
            "event_id": row["event_id"],
            "table": row["table_name"],
            "occurred_at": datetime.fromtimestamp(
                row["occurred_us"] / 1_000_000, timezone.utc
            ).isoformat(),
            "operation": row["operation"],
            "data": data,
        }
        if row["local_id"] is not None:
            item["local_id"] = row["local_id"]
        candidate = json.dumps(
            {"version": 1, "source_id": state["source_id"], "events": events + [item]},
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if len(candidate) > MAX_BYTES:
            if not events:
                raise ValueError("One event exceeds the API body limit; event retained")
            break
        events.append(item)
        body = candidate
    if not events:
        return 0
    result = transport(
        state["url"], cipher.decrypt(state["project_key"]).decode(), body, timeout
    )
    sent = {item["event_id"] for item in events}
    acknowledged = result.get("acknowledged_event_ids")
    if not isinstance(acknowledged, list) or set(acknowledged) != sent:
        raise ValueError(
            "Incomplete acknowledgement; batch retained to preserve parent ordering"
        )
    replacement = result.get("replacement_key")
    if replacement is not None and (
        not isinstance(replacement, str) or not replacement.startswith("pgw_")
    ):
        raise ValueError("Invalid replacement key; batch retained")
    with connection:
        if replacement:
            connection.execute(
                "UPDATE sender_state SET project_key=?",
                (cipher.encrypt(replacement.encode()),),
            )
        connection.executemany(
            "DELETE FROM sender_outbox WHERE event_id=?",
            [(event_id,) for event_id in sent],
        )
    return len(events)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument(
        "--set-key",
        action="store_true",
        help="Explicitly replace the persisted project key",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    path = Path(os.environ["COLLECTOR_SQLITE_PATH"]).resolve()
    # One sender owns delivery. The collector continues writing via WAL.
    import fcntl

    with path.with_suffix(".sender.lock").open("a") as lock:
        # Compose can rerun the completed initialization service while the
        # sender is already running. Initialization only takes a SQLite lock.
        if not args.init_only:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())
        connection = connect(path)
        try:
            initialize(
                connection,
                os.environ["SENDER_URL"],
                os.getenv("SENDER_PROJECT_KEY", ""),
                cipher,
                set_key=args.set_key,
            )
            if args.init_only or args.set_key:
                return
            interval = float(os.getenv("SENDER_INTERVAL", "5"))
            timeout = float(os.getenv("SENDER_TIMEOUT", "30"))
            batch_size = int(os.getenv("SENDER_BATCH_SIZE", "250"))
            if interval <= 0 or timeout <= 0 or not 1 <= batch_size <= 500:
                raise ValueError(
                    "Invalid sender interval, timeout or batch size (1..500)"
                )
            failures = 0
            while True:
                try:
                    count = deliver(connection, cipher, batch_size, timeout)
                    failures = 0
                    if count:
                        logging.info("Acknowledged %s events", count)
                        continue
                except Exception as error:
                    failures = min(failures + 1, 6)
                    detail = (
                        str(error)
                        if isinstance(error, DeliveryError)
                        else type(error).__name__
                    )
                    logging.error(
                        "Delivery failed (%s); pending events retained", detail
                    )
                time.sleep(min(60, interval * 2**failures))
        finally:
            connection.close()


if __name__ == "__main__":
    main()
