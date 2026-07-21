import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from notifier.services.rules import RULE_TYPES


DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_COOLDOWN_SECONDS = 30 * 60
DEFAULT_WINDOW_MINUTES = 5

CHANNEL_NAMES = ("slack", "discord", "teams", "email")
SCOPE_NAMES = ("server", "database", "table", "index")

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


@dataclass(frozen=True)
class Threshold:
    warning: float
    critical: float
    direction: str = "above"

    def severity_for(self, value: float) -> str | None:
        if self.direction == "below":
            if value <= self.critical:
                return "critical"
            if value <= self.warning:
                return "warning"
            return None
        if value >= self.critical:
            return "critical"
        if value >= self.warning:
            return "warning"
        return None


@dataclass(frozen=True)
class ChannelYamlConfig:
    name: str
    enabled: bool
    credentials: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetYamlConfig:
    scope: str
    type: str
    names: list[dict[str, str]]
    filters: dict[str, Any]
    warning: float
    critical: float
    direction: str


@dataclass(frozen=True)
class RuleYamlConfig:
    name: str
    interval: int
    cooldown: int
    window_minutes: int
    enabled: bool
    targets: list[TargetYamlConfig] = field(default_factory=list)


@dataclass(frozen=True)
class NotifierYamlConfig:
    channels: dict[str, ChannelYamlConfig] = field(default_factory=dict)
    rules: list[RuleYamlConfig] = field(default_factory=list)


def load_notifier_config() -> NotifierYamlConfig:
    raw = _load_raw_config()
    section = _notifier_section(raw)

    channels: dict[str, ChannelYamlConfig] = {}
    raw_channels = section.get("channels") or {}
    for name in CHANNEL_NAMES:
        entry = raw_channels.get(name)
        if entry is None:
            continue
        if isinstance(entry, bool):
            entry = {"enabled": entry}
        channels[name] = ChannelYamlConfig(
            name=name,
            enabled=_bool(entry.get("enabled", False)),
            credentials=entry.get("credentials") or {},
        )

    rules = [_parse_rule(entry) for entry in _rule_entries(section.get("rules"))]
    return NotifierYamlConfig(channels=channels, rules=[rule for rule in rules if rule])


def _parse_rule(entry: dict[str, Any]) -> RuleYamlConfig | None:
    name = entry.get("name")
    if not name:
        return None

    targets: list[TargetYamlConfig] = []
    for scope in SCOPE_NAMES:
        for target in _target_entries(entry.get(scope)):
            parsed = _parse_target(scope, target)
            if parsed:
                targets.append(parsed)

    return RuleYamlConfig(
        name=str(name),
        interval=max(5, _int(entry.get("interval"), DEFAULT_INTERVAL_SECONDS)),
        cooldown=max(0, _int(entry.get("cooldown"), DEFAULT_COOLDOWN_SECONDS)),
        window_minutes=max(1, _int(entry.get("window_minutes"), DEFAULT_WINDOW_MINUTES)),
        enabled=_bool(entry.get("enabled", True)),
        targets=targets,
    )


def _parse_target(scope: str, entry: dict[str, Any]) -> TargetYamlConfig | None:
    rule_type = entry.get("type")
    known = RULE_TYPES.get((scope, str(rule_type)))
    if known is None:
        return None

    names = _parse_names(scope, entry)
    filters = {} if names else _parse_filters(scope, entry)
    return TargetYamlConfig(
        scope=scope,
        type=str(rule_type),
        names=names,
        filters=filters,
        warning=_float(entry.get("warning"), known.default_warning),
        critical=_float(entry.get("critical"), known.default_critical),
        direction=str(entry.get("direction", known.default_direction)),
    )


def _parse_names(scope: str, entry: dict[str, Any]) -> list[dict[str, str]]:
    if scope == "server":
        return [{"server": name} for name in _str_list(entry, "servers", "server")]

    if scope == "database":
        return [{"database": name} for name in _str_list(entry, "databases", "database")]

    if scope == "table":
        tables = entry.get("tables")
        if isinstance(tables, list):
            return [_parse_table_name(item) for item in tables if item]
        if entry.get("table"):
            return [_parse_table_name(entry)]
        return []

    if scope == "index":
        indexes = entry.get("indexes")
        if isinstance(indexes, list):
            return [_parse_index_name(item) for item in indexes if item]
        if entry.get("index"):
            return [_parse_index_name(entry)]
        return []

    return []


def _parse_table_name(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        parsed = {key: str(item[key]) for key in ("database", "schema", "table") if item.get(key)}
        parsed.setdefault("schema", "public")
        return parsed

    parts = str(item).split(".")
    if len(parts) >= 3:
        return {"database": parts[0], "schema": parts[1], "table": parts[2]}
    if len(parts) == 2:
        return {"schema": parts[0], "table": parts[1]}
    return {"schema": "public", "table": parts[0]}


def _parse_index_name(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        return {key: str(item[key]) for key in ("database", "index") if item.get(key)}

    parts = str(item).split(".")
    if len(parts) >= 2:
        return {"database": parts[0], "index": parts[1]}
    return {"index": parts[0]}


def _parse_filters(scope: str, entry: dict[str, Any]) -> dict[str, Any]:
    if scope == "table":
        filters: dict[str, Any] = {}
        if entry.get("database"):
            filters["database"] = str(entry["database"])
        schemas = entry.get("schemas")
        if isinstance(schemas, list) and schemas:
            filters["schemas"] = [str(schema) for schema in schemas]
        if entry.get("table_regex"):
            filters["table_regex"] = str(entry["table_regex"])
        return filters

    if scope == "index":
        filters = {}
        if entry.get("database"):
            filters["database"] = str(entry["database"])
        tables = entry.get("tables")
        if isinstance(tables, list) and tables:
            filters["tables"] = [str(table) for table in tables]
        if entry.get("index_regex"):
            filters["index_regex"] = str(entry["index_regex"])
        return filters

    return {}


def _str_list(entry: dict[str, Any], plural: str, singular: str) -> list[str]:
    value = entry.get(plural)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if entry.get(singular):
        return [str(entry[singular])]
    return []


def _rule_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    if isinstance(value, dict):
        return [{"name": name, **config} for name, config in value.items() if isinstance(config, dict)]
    return []


def _target_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _load_raw_config() -> dict[str, Any]:
    for path in _candidate_paths():
        if not path.exists():
            continue

        with path.open(encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
            loaded = loaded if isinstance(loaded, dict) else {}
            return _interpolate_env(loaded)

    return {}


def _interpolate_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda match: os.environ.get(match.group(1), match.group(2) or ""),
            value,
        )
    if isinstance(value, dict):
        return {key: _interpolate_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


def _candidate_paths() -> list[Path]:
    project_root = Path(__file__).resolve().parents[2]
    return [
        Path("notifier.yaml"),
        Path("notifier.yml"),
        Path("config.yaml"),
        Path("config.yml"),
        project_root / "notifier.yaml",
        project_root / "notifier.yml",
        project_root / "config.yaml",
        project_root / "config.yml",
        project_root / "notifier" / "config.yaml",
        Path("/etc/pgwarden/notifier.yaml"),
        Path("/etc/pgwarden/notifier.yml"),
    ]


def _notifier_section(raw: dict[str, Any]) -> dict[str, Any]:
    if "notifier" in raw and isinstance(raw["notifier"], dict):
        return raw["notifier"]

    if any(key in raw for key in ("channels", "rules")):
        return raw

    return {}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
