"""Adapt scoped logical estimates for the existing defaults editor."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.retention.models import RetentionWindow
from app.retention.scoped_preview import preview_scope
from app.retention.scopes import GLOBAL_ID


async def preview_default(
    session: AsyncSession, policy: dict[str, Any], window: RetentionWindow,
) -> dict[str, Any]:
    """Keep the default editor truthful about row deletion and logical storage."""
    result = await preview_scope(session, "global", GLOBAL_ID, policy["name"], window)
    return {"name": policy["name"], "window": window.model_dump(),
            "measured_at": result["measured_at"], "cutoff": result["measured_at"],
            "current_policy": policy, "current_bytes": result["logical_bytes"],
            "projected_bytes": result["projected_bytes"], "baseline_projected_bytes": None,
            "policy_delta_bytes": None, "footprint_delta_bytes": None,
            "bytes_per_day": None, "reclaimable_bytes": result["expired_bytes"],
            "eligible_chunks": 0, "total_chunks": 0, "compressed_chunks": 0,
            "observed_seconds": 0, "first_sample": None, "last_sample": None,
            "confidence": "limited" if result["projected_bytes"] is not None else "insufficient_data",
            "logical": True, "expired_rows": result["expired_rows"]}
