from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_INTERVAL_SECONDS = 30 * 60
MIN_INTERVAL_SECONDS = 10


@dataclass(frozen=True)
class DatabaseAnalyticsYamlConfig:
    name: str
    interval: int
    query_analysis: bool
    recommendation: bool


@dataclass(frozen=True)
class AnalyticsYamlConfig:
    interval: int = DEFAULT_INTERVAL_SECONDS
    query_analysis: bool = True
    recommendation: bool = True
    databases: dict[str, DatabaseAnalyticsYamlConfig] | None = None

    def for_database(self, name: str | None) -> DatabaseAnalyticsYamlConfig:
        if name and self.databases and name in self.databases:
            return self.databases[name]

        return DatabaseAnalyticsYamlConfig(
            name=name or "",
            interval=self.interval,
            query_analysis=self.query_analysis,
            recommendation=self.recommendation,
        )


def load_analytics_config() -> AnalyticsYamlConfig:
    raw = _load_raw_config()
    analytics = _analytics_section(raw)
    defaults = analytics.get("defaults") or analytics.get("default") or {}

    default_interval = _interval(defaults.get("interval", analytics.get("interval", DEFAULT_INTERVAL_SECONDS)))
    default_query_analysis = _bool(
        defaults.get("query_analysis", analytics.get("query_analysis", analytics.get("query_analytics", True)))
    )
    default_recommendation = _bool(defaults.get("recommendation", analytics.get("recommendation", True)))

    databases: dict[str, DatabaseAnalyticsYamlConfig] = {}
    for entry in _database_entries(analytics.get("databases")):
        name = entry.get("name")
        if not name:
            continue

        databases[str(name)] = DatabaseAnalyticsYamlConfig(
            name=str(name),
            interval=_interval(entry.get("interval", default_interval)),
            query_analysis=_bool(entry.get("query_analysis", entry.get("query_analytics", default_query_analysis))),
            recommendation=_bool(entry.get("recommendation", default_recommendation)),
        )

    return AnalyticsYamlConfig(
        interval=default_interval,
        query_analysis=default_query_analysis,
        recommendation=default_recommendation,
        databases=databases,
    )


def _load_raw_config() -> dict[str, Any]:
    for path in _candidate_paths():
        if not path.exists():
            continue

        with path.open(encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
            return loaded if isinstance(loaded, dict) else {}

    return {}


def _candidate_paths() -> list[Path]:
    project_root = Path(__file__).resolve().parents[2]
    return [
        Path("analytics.yaml"),
        Path("analytics.yml"),
        Path("config.yaml"),
        Path("config.yml"),
        project_root / "analytics.yaml",
        project_root / "analytics.yml",
        project_root / "analytics" / "config.yaml",
        project_root / "analytics" / "config.yml",
        Path("/etc/pgwarden/analytics.yaml"),
        Path("/etc/pgwarden/analytics.yml"),
    ]


def _analytics_section(raw: dict[str, Any]) -> dict[str, Any]:
    if "analytics" in raw and isinstance(raw["analytics"], dict):
        return raw["analytics"]

    if any(key in raw for key in ("defaults", "default", "databases", "interval", "query_analysis", "recommendation")):
        return raw

    return {}


def _database_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]

    if isinstance(value, dict):
        entries = []
        for name, config in value.items():
            if isinstance(config, dict):
                entries.append({"name": name, **config})
            else:
                entries.append({"name": name})
        return entries

    return []


def _interval(value: Any) -> int:
    try:
        return max(MIN_INTERVAL_SECONDS, int(value))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_SECONDS


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
