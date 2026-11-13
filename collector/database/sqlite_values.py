"""Convert PostgreSQL collection values to SQLite's portable scalar types."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID


JSON_FIELDS = {
    "ignore_patterns",
    "ignore_tables",
    "include_tables",
    "payload",
    "errors",
    "columns_info",
}
TIME_FIELDS = {
    "next_run_at",
    "stats_reset",
    "collected_at",
    "backend_start",
    "xact_start",
    "query_start",
    "state_change",
    "stats_since",
    "minmax_stats_since",
    "last_vacuum",
    "last_autovacuum",
    "last_analyze",
    "last_autoanalyze",
}


def encode_value(value: object) -> object:
    """Serialize values unsupported by SQLite's DB-API bindings."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (IPv4Address, IPv6Address, UUID)):
        return str(value)
    return value


def decode_value(name: str, value: object) -> object:
    """Restore JSON and timezone-aware scheduling values."""
    if value is None:
        return None
    if name.startswith("is_"):
        return bool(value)
    if name in JSON_FIELDS:
        return json.loads(value)
    if name in TIME_FIELDS or name.endswith("_at"):
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
    return value
