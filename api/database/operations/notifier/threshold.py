from typing import Type

from database.operations.interface import Interface
from database.models.notifier import (
    RuleServer,
    RuleDatabase,
    RuleTable,
    RuleIndex,
)


class ThresholdRepository(Interface):
    def __init__(self, model: Type, db):
        super().__init__(model, db)


_SCOPE_REPOS = {
    "server": (RuleServer, "server_id"),
    "database": (RuleDatabase, "database_id"),
    "table": (RuleTable, "table_id"),
    "index": (RuleIndex, "index_id"),
}


def get_threshold_scope(scope: str) -> tuple[type, str]:
    if scope not in _SCOPE_REPOS:
        raise ValueError(f"Invalid threshold scope: {scope}")
    return _SCOPE_REPOS[scope]


def threshold_repository(scope: str, db) -> ThresholdRepository:
    model, _ = get_threshold_scope(scope)
    return ThresholdRepository(model, db)
