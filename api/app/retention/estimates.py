"""Estimate storage from physical chunks and observed collection history."""

from datetime import datetime
from typing import Any


def estimate_storage(
    chunks: list[dict[str, Any]],
    first_sample: datetime | None,
    last_sample: datetime | None,
    measured_at: datetime,
    cutoff: datetime,
    target_seconds: float,
    current_seconds: float | None,
) -> dict[str, Any]:
    """Project a steady footprint and count whole chunks eligible for removal.

    The observed physical bytes include indexes, TOAST and compression. The
    observation ends now so a stopped collector does not imply ongoing growth.
    """
    current_bytes = sum(int(chunk["total_bytes"]) for chunk in chunks)
    observed_seconds = (
        max(0.0, (measured_at - first_sample).total_seconds())
        if first_sample is not None else 0.0
    )
    has_history = (
        first_sample is not None and last_sample is not None
        and last_sample > first_sample and observed_seconds >= 60
    )
    rate = current_bytes / observed_seconds if has_history else None
    projected = round(rate * target_seconds) if rate is not None else None
    baseline = (
        round(rate * current_seconds)
        if rate is not None and current_seconds is not None else None
    )
    eligible = [chunk for chunk in chunks if chunk["range_end"] <= cutoff]
    return {
        "current_bytes": current_bytes,
        "observed_seconds": observed_seconds,
        "first_sample": first_sample,
        "last_sample": last_sample,
        "bytes_per_day": round(rate * 86400) if rate is not None else None,
        "projected_bytes": projected,
        "baseline_projected_bytes": baseline,
        "policy_delta_bytes": projected - baseline
        if projected is not None and baseline is not None else None,
        "footprint_delta_bytes": projected - current_bytes
        if projected is not None else None,
        "reclaimable_bytes": sum(int(chunk["total_bytes"]) for chunk in eligible),
        "eligible_chunks": len(eligible),
        "total_chunks": len(chunks),
        "compressed_chunks": sum(bool(chunk["is_compressed"]) for chunk in chunks),
        "confidence": "limited" if has_history else "insufficient_data",
    }
