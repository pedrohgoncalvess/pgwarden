"""Replicate retention across all current metric hypertables."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.retention import services
from app.retention.models import RetentionWindow


def sum_estimates(previews: list[dict[str, Any]], key: str) -> int | None:
    """Keep consolidated estimates unknown if any table lacks an estimate."""
    values = [preview[key] for preview in previews]
    return None if any(value is None for value in values) else sum(values)


async def get_targets(session: AsyncSession) -> list[dict[str, Any]]:
    """Resolve all currently available metric hypertables in lock order."""
    policies = await services.list_policies(session)
    if not policies:
        raise HTTPException(404, "No metric hypertables are available.")
    return sorted(policies, key=lambda policy: policy["name"])


async def preview_global(
    session: AsyncSession, window: RetentionWindow
) -> dict[str, Any]:
    """Combine table previews without extrapolating missing table histories."""
    targets = await get_targets(session)
    previews = [await services.preview_policy(session, policy["name"], window)
                for policy in targets]
    first_samples = [item["first_sample"] for item in previews if item["first_sample"]]
    last_samples = [item["last_sample"] for item in previews if item["last_sample"]]
    totals = {key: sum_estimates(previews, key) for key in (
        "current_bytes", "bytes_per_day", "projected_bytes",
        "baseline_projected_bytes", "policy_delta_bytes", "footprint_delta_bytes",
        "reclaimable_bytes", "eligible_chunks", "total_chunks", "compressed_chunks",
    )}
    return {
        "name": "__all__", "window": window.model_dump(),
        "measured_at": previews[0]["measured_at"], "cutoff": previews[0]["cutoff"],
        "current_policy": None, "tables": previews,
        "observed_seconds": max(item["observed_seconds"] for item in previews),
        "first_sample": min(first_samples) if first_samples else None,
        "last_sample": max(last_samples) if last_samples else None,
        "confidence": "insufficient_data" if any(
            item["confidence"] == "insufficient_data" for item in previews
        ) else "limited",
        **totals,
    }


async def update_global(
    session: AsyncSession, window: RetentionWindow
) -> list[dict[str, Any]]:
    """Apply all policy updates atomically, preserving each job's schedule."""
    try:
        targets = await get_targets(session)
        for policy in targets:
            await services.apply_policy(session, policy["name"], window)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return await services.list_policies(session)
