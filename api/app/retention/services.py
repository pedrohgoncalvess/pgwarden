"""Read and update the actual TimescaleDB jobs transactionally."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.estimates import estimate_storage
from app.retention.models import RetentionWindow
from app.retention.queries import CHUNKS, TABLES, WINDOW


async def list_policies(session: AsyncSession) -> list[dict[str, Any]]:
    """List metric hypertables and their current retention jobs."""
    if await session.scalar(text("SELECT to_regclass('retention.policy')")):
        from app.retention.managed import list_defaults
        return await list_defaults(session)
    installed = await session.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')"
    ))
    if not installed:
        raise HTTPException(503, "TimescaleDB is not installed in the metrics database.")
    return [dict(row) for row in (await session.execute(TABLES)).mappings()]


async def get_policy(session: AsyncSession, name: str) -> dict[str, Any]:
    """Resolve names against the Timescale catalog before building identifiers."""
    for policy in await list_policies(session):
        if policy["name"] == name:
            return policy
    raise HTTPException(404, "Metric hypertable not found.")


def get_relation(name: str) -> str:
    """Quote a catalog-sourced table name as a PostgreSQL identifier."""
    return '"metric"."' + name.replace('"', '""') + '"'


async def preview_policy(
    session: AsyncSession, name: str, window: RetentionWindow
) -> dict[str, Any]:
    """Estimate the proposed interval using a consistent transaction timestamp."""
    policy = await get_policy(session, name)
    if policy.get("managed"):
        from app.retention.managed_preview import preview_default
        return await preview_default(session, policy, window)
    relation = get_relation(name)
    interval = f"{window.value} {window.unit}"
    timing = (await session.execute(WINDOW, {"interval": interval})).mappings().one()
    chunks = [dict(row) for row in (await session.execute(
        CHUNKS, {"relation": relation, "name": name}
    )).mappings()]
    samples = (await session.execute(text(f"""
        SELECT (SELECT collected_at FROM {relation}
                ORDER BY collected_at ASC LIMIT 1) AS first_sample,
               (SELECT collected_at FROM {relation}
                ORDER BY collected_at DESC LIMIT 1) AS last_sample
    """))).mappings().one()
    estimate = estimate_storage(
        chunks, samples["first_sample"], samples["last_sample"],
        timing["measured_at"], timing["cutoff"], float(timing["seconds"]),
        float(policy["retention_seconds"])
        if policy["retention_seconds"] is not None else None,
    )
    return {
        "name": name, "window": window.model_dump(),
        "measured_at": timing["measured_at"], "cutoff": timing["cutoff"],
        "current_policy": policy, **estimate,
    }


async def apply_policy(
    session: AsyncSession, name: str, window: RetentionWindow
) -> None:
    """Patch a policy without committing the surrounding transaction."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                          {"key": f"pgwarden:retention:{name}"})
    policy = await get_policy(session, name)
    if policy.get("managed"):
        from app.retention.scopes import GLOBAL_ID, save_policy
        await save_policy(session, "global", GLOBAL_ID, name, window)
        return
    params = {"interval": f"{window.value} {window.unit}"}
    if policy["job_id"] is None:
        await session.execute(text("""
            SELECT add_retention_policy(CAST(:relation AS regclass),
                                        drop_after => CAST(CAST(:interval AS text) AS interval))
        """), {**params, "relation": get_relation(name)})
    else:
        await session.execute(text("""
            SELECT alter_job(job_id, config =>
                (config - 'drop_created_before') ||
                jsonb_build_object('drop_after', CAST(:interval AS text)))
            FROM timescaledb_information.jobs WHERE job_id = :job_id
        """), {**params, "job_id": policy["job_id"]})


async def update_policy(
    session: AsyncSession, name: str, window: RetentionWindow
) -> dict[str, Any]:
    """Save one policy, preserving its configuration and schedule."""
    await apply_policy(session, name, window)
    await session.commit()
    return await get_policy(session, name)
