"""Build normalized query summaries from compact SQL statistics."""

from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import Row

from app.databases.analytics.query.models import (
    QueryAnalyticsApplicationBreakdown, QueryAnalyticsItem,
    QueryAnalyticsTimelinePoint, QueryAnalyticsUserBreakdown,
)


def _merge_duration(target: dict, row: Row) -> None:
    target["count"] += row.execution_count
    target["duration_count"] += row.duration_count
    target["duration_sum"] += row.duration_sum or 0
    if row.duration_count and row.duration_min is not None and row.duration_max is not None:
        target["duration_min"] = min(target["duration_min"], row.duration_min)
        target["duration_max"] = max(target["duration_max"], row.duration_max)


def _new_summary() -> dict:
    return {
        "count": 0, "duration_count": 0, "duration_sum": 0,
        "duration_min": float("inf"), "duration_max": float("-inf"),
        "users": Counter(), "applications": Counter(),
    }


def _duration(summary: dict, field: str) -> float | None:
    if not summary["duration_count"]:
        return None
    if field == "avg":
        return summary["duration_sum"] / summary["duration_count"]
    value = summary[f"duration_{field}"]
    return value if isfinite(value) else None


def _build_item(signature: str, summary: dict) -> QueryAnalyticsItem:
    preview = signature if len(signature) <= 120 else signature[:120].rstrip() + "..."
    return QueryAnalyticsItem(
        query_signature=signature, query_preview=preview,
        query_hash=summary["query_hash"], execution_count=summary["count"],
        avg_duration_ms=_duration(summary, "avg"),
        min_duration_ms=_duration(summary, "min"),
        max_duration_ms=_duration(summary, "max"),
        total_duration_ms=_duration(summary, "sum"),
        unique_users=len(summary["users"]),
        user_breakdown=[
            QueryAnalyticsUserBreakdown(user_name=name, execution_count=count)
            for name, count in summary["users"].most_common()
        ],
        unique_applications=len(summary["applications"]),
        application_breakdown=[
            QueryAnalyticsApplicationBreakdown(
                application_name=name, execution_count=count,
            )
            for name, count in summary["applications"].most_common()
        ],
        first_seen=summary["first_seen"], last_seen=summary["last_seen"],
        sources=sorted(summary.get("sources", {"activity"})),
        pg_query_id=str(summary["pg_query_id"]) if summary.get("pg_query_id") else None,
        query_hashes=sorted(summary.get("hashes", set())),
        query_texts=sorted(summary.get("texts", set())),
        activity_executions=summary.get("activity_executions", summary["count"]),
        statements_calls=summary.get("statements_calls"),
        metrics_source=summary.get("metrics_source", "activity"),
    )


def summarize_queries(
    rows: Sequence[Row], normalize: Callable[[str | None], str],
    search: list[str], exclude: list[str], limit: int | None,
    order_by: str, order_dir: str,
) -> tuple[list[QueryAnalyticsItem], list[QueryAnalyticsTimelinePoint], int]:
    """Merge hash statistics while keeping equally weighted execution averages."""
    signatures: dict[tuple, dict] = {}
    timeline: dict[datetime, dict] = {}
    normalized: dict[tuple, str] = {}
    text_ids: dict[str, set] = {}
    for row in rows:
        if getattr(row, "pg_query_id", None):
            text_ids.setdefault(row.query, set()).add(row.pg_query_id)
    for row in rows:
        key = (row.query_hash, row.query if row.query_hash is None else None)
        if key not in normalized:
            normalized[key] = normalize(row.query)
        signature = normalized[key]
        if not signature or (search and not any(term in signature for term in search)):
            continue
        if any(term in signature for term in exclude):
            continue
        pg_id = getattr(row, "pg_query_id", None)
        if not pg_id and len(text_ids.get(row.query, set())) == 1:
            pg_id = next(iter(text_ids[row.query]))
        identity = ("pg", pg_id) if pg_id else ("text", signature)
        if identity not in signatures:
            signatures[identity] = _new_summary() | {
                "query_hash": f"pg:{pg_id}" if pg_id else row.query_hash,
                "first_seen": row.first_seen, "last_seen": row.last_seen,
                "signature": signature, "pg_query_id": pg_id,
                "sources": set(), "hashes": set(), "texts": set(),
                "activity": _new_summary(), "statements": _new_summary(),
                "has_delta": False,
            }
        summary = signatures[identity]
        source = getattr(row, "source", "activity")
        summary["sources"].add(source)
        if row.query_hash:
            summary["hashes"].add(row.query_hash)
        summary["texts"].add(row.query)
        component = summary[source]
        _merge_duration(component, row)
        component["users"][row.user_name] += row.execution_count
        component["applications"][row.application_name] += row.execution_count
        summary["has_delta"] |= source == "statements" and getattr(row, "delta_valid", False)
        summary["first_seen"] = min(summary["first_seen"], row.first_seen)
        summary["last_seen"] = max(summary["last_seen"], row.last_seen)

        if source != "activity":
            continue
        bucket = datetime.fromtimestamp(float(row.bucket) * 300, tz=timezone.utc)
        if bucket not in timeline:
            timeline[bucket] = _new_summary()
        _merge_duration(timeline[bucket], row)

    for summary in signatures.values():
        use_statements = summary["has_delta"]
        selected = summary["statements"] if use_statements else summary["activity"]
        summary.update(selected)
        summary["activity_executions"] = summary["activity"]["count"]
        summary["statements_calls"] = summary["statements"]["count"] if use_statements else None
        summary["metrics_source"] = "statements" if use_statements else ("activity" if "activity" in summary["sources"] else "unavailable")

    sort_field = {
        "avg_duration": "avg", "max_duration": "max", "total_duration": "sum",
    }.get(order_by)

    def sort_key(item: tuple[tuple, dict]) -> tuple[float, str]:
        _, summary = item
        value = _duration(summary, sort_field) if sort_field else summary["count"]
        return value or 0, summary["signature"]

    ordered = sorted(signatures.items(), key=sort_key, reverse=order_dir == "desc")
    page = ordered[:limit] if limit else ordered
    return (
        [_build_item(summary["signature"], summary) for _, summary in page],
        [QueryAnalyticsTimelinePoint(
            timestamp=bucket, execution_count=summary["count"],
            avg_duration_ms=_duration(summary, "avg"),
        ) for bucket, summary in sorted(timeline.items())],
        len(signatures),
    )
