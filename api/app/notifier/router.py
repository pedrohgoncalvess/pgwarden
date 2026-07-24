import json
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from app.notifier.models import (
    ChannelPatch,
    ChannelResponse,
    RuleCreate,
    RulePatch,
    RuleResponse,
    ThresholdCreate,
    ThresholdPatch,
    ThresholdResponse,
)
from database.connection import DatabaseConnection
from database.models.notifier.rule import NotifierRule
from database.operations.collector.server import ServerRepository
from database.operations.metadata.database import DatabaseRepository
from database.operations.metadata.index import IndexRepository
from database.operations.metadata.table import TableRepository
from database.operations.notifier import (
    NotifierChannelRepository,
    NotifierRuleRepository,
    get_threshold_scope,
    threshold_repository,
)
from utils import encrypt


router = APIRouter(
    prefix="/notifier",
    tags=["notifier"],
    dependencies=[Depends(get_current_user)],
)


_SCOPE_ENTITY_ATTR = {
    "server": "server_id",
    "database": "database_id",
    "table": "table_id",
    "index": "index_id",
}

_ENTITY_REPOS = {
    "server": ServerRepository,
    "database": DatabaseRepository,
    "table": TableRepository,
    "index": IndexRepository,
}

# Rule types implemented by the notifier evaluator (mirrors notifier/services/rules.py).
RULE_TYPE_OPTIONS: Dict[str, List[str]] = {
    "server": ["cpu_percent", "ram_percent", "disk_percent"],
    "database": [
        "growth_percent",
        "cache_hit_ratio",
        "deadlocks",
        "tup_updated",
        "tup_deleted",
        "long_query_ms",
        "waiting_sessions",
        "blocked_locks",
        "table_created",
        "table_dropped",
        "index_created",
        "index_dropped",
    ],
    "table": ["growth_percent", "dead_tuples", "dead_tuple_ratio", "column_added"],
    "index": ["hit_rate"],
}


def _validate_scope(scope: str) -> None:
    try:
        get_threshold_scope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid threshold scope: {scope}")


async def _resolve_entity_public_id(conn, scope: str, entity_id: Optional[int]) -> Optional[UUID]:
    if entity_id is None:
        return None
    repo = _ENTITY_REPOS[scope](conn)
    entity = await repo.find_by_id(entity_id)
    return entity.public_id if entity else None


async def _resolve_entity_id(conn, scope: str, entity_public_id: Optional[UUID]) -> Optional[int]:
    if entity_public_id is None:
        return None
    repo = _ENTITY_REPOS[scope](conn)
    entity = await repo.find_one_by(public_id=entity_public_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"{scope.capitalize()} not found")
    return entity.id


async def _threshold_response(conn, scope: str, row) -> ThresholdResponse:
    entity_attr = _SCOPE_ENTITY_ATTR[scope]
    entity_id = getattr(row, entity_attr)
    return ThresholdResponse(
        id=row.id,
        rule_id=row.rule_id,
        scope=scope,
        type=row.type,
        entity_id=entity_id,
        entity_public_id=await _resolve_entity_public_id(conn, scope, entity_id),
        warning=row.warning,
        critical=row.critical,
        direction=row.direction,
    )


async def _load_thresholds(conn, rule_id: int) -> List[ThresholdResponse]:
    thresholds: List[ThresholdResponse] = []
    for scope in ("server", "database", "table", "index"):
        repo = threshold_repository(scope, conn)
        rows = await repo.find_by(rule_id=rule_id)
        for row in rows:
            thresholds.append(await _threshold_response(conn, scope, row))
    return thresholds


def _rule_response(rule, thresholds: List[ThresholdResponse]) -> RuleResponse:
    return RuleResponse(
        **{k: getattr(rule, k) for k in rule.__dict__ if not k.startswith("_")},
        thresholds=thresholds,
    )


@router.get(
    "/rule-types",
    response_model=Dict[str, List[str]],
    summary="List available rule types",
    description="Returns the rule types implemented by the notifier evaluator, grouped by scope.",
    responses={**COMMON_RESPONSES},
)
async def list_rule_types():
    return RULE_TYPE_OPTIONS


@router.get(
    "/rules",
    response_model=List[RuleResponse],
    summary="List alert rules",
    description="Returns all notifier rules with their thresholds grouped by scope.",
    responses={**COMMON_RESPONSES},
)
async def list_rules():
    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        rules = await rule_repo.find_all()
        return [
            _rule_response(rule, await _load_thresholds(conn, rule.id))
            for rule in rules
        ]


@router.post(
    "/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
    description="Creates a new notifier rule. Thresholds are added via the thresholds endpoint.",
    responses={
        409: {"model": ErrorMessage, "description": "Rule name already exists"},
        **COMMON_RESPONSES,
    },
)
async def create_rule(payload: RuleCreate):
    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        rule = NotifierRule(**payload.model_dump())
        try:
            created = await rule_repo.insert(rule)
        except ValueError:
            raise HTTPException(status_code=409, detail="Rule name already exists")

        return _rule_response(created, [])


@router.get(
    "/rules/{rule_id}",
    response_model=RuleResponse,
    summary="Get an alert rule",
    description="Returns a single rule and all its thresholds.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule not found"},
        **COMMON_RESPONSES,
    },
)
async def get_rule(rule_id: int):
    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        rule = await rule_repo.find_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        return _rule_response(rule, await _load_thresholds(conn, rule.id))


@router.patch(
    "/rules/{rule_id}",
    response_model=RuleResponse,
    summary="Update alert rule metadata",
    description="Partially updates rule scheduling and enablement settings.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule not found"},
        400: {"model": ErrorMessage, "description": "No fields to update"},
        **COMMON_RESPONSES,
    },
)
async def patch_rule(rule_id: int, patch: RulePatch):
    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        rule = await rule_repo.find_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        updates = patch.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = await rule_repo.update(rule_id, updates)
        return _rule_response(updated, await _load_thresholds(conn, updated.id))


@router.post(
    "/rules/{rule_id}/thresholds",
    response_model=ThresholdResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a threshold",
    description="Adds a scoped threshold to a rule. Omit entity_public_id to target all entities of the scope.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule or entity not found"},
        400: {"model": ErrorMessage, "description": "Invalid scope or rule type"},
        409: {"model": ErrorMessage, "description": "Threshold already exists for this rule, type and entity"},
        **COMMON_RESPONSES,
    },
)
async def create_threshold(rule_id: int, payload: ThresholdCreate):
    _validate_scope(payload.scope)

    if payload.type not in RULE_TYPE_OPTIONS[payload.scope]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid rule type '{payload.type}' for scope '{payload.scope}'",
        )

    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        if not await rule_repo.find_by_id(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        entity_id = await _resolve_entity_id(conn, payload.scope, payload.entity_public_id)

        model, entity_attr = get_threshold_scope(payload.scope)
        repo = threshold_repository(payload.scope, conn)
        row = model(
            rule_id=rule_id,
            type=payload.type,
            warning=payload.warning,
            critical=payload.critical,
            direction=payload.direction,
            **{entity_attr: entity_id},
        )
        try:
            created = await repo.insert(row)
        except ValueError:
            raise HTTPException(
                status_code=409,
                detail="Threshold already exists for this rule, type and entity",
            )

        return await _threshold_response(conn, payload.scope, created)


@router.get(
    "/rules/{rule_id}/thresholds/{scope}/{threshold_id}",
    response_model=ThresholdResponse,
    summary="Get a threshold",
    description="Returns a single threshold override for a rule.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule or threshold not found"},
        400: {"model": ErrorMessage, "description": "Invalid scope"},
        **COMMON_RESPONSES,
    },
)
async def get_threshold(rule_id: int, scope: str, threshold_id: int):
    _validate_scope(scope)

    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        if not await rule_repo.find_by_id(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        repo = threshold_repository(scope, conn)
        row = await repo.find_by_id(threshold_id)
        if not row or row.rule_id != rule_id:
            raise HTTPException(status_code=404, detail="Threshold not found")

        return await _threshold_response(conn, scope, row)


@router.patch(
    "/rules/{rule_id}/thresholds/{scope}/{threshold_id}",
    response_model=ThresholdResponse,
    summary="Update a threshold",
    description="Partially updates warning, critical and direction values of a threshold.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule or threshold not found"},
        400: {"model": ErrorMessage, "description": "Invalid scope or no fields to update"},
        **COMMON_RESPONSES,
    },
)
async def patch_threshold(rule_id: int, scope: str, threshold_id: int, patch: ThresholdPatch):
    _validate_scope(scope)

    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        if not await rule_repo.find_by_id(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        repo = threshold_repository(scope, conn)
        row = await repo.find_by_id(threshold_id)
        if not row or row.rule_id != rule_id:
            raise HTTPException(status_code=404, detail="Threshold not found")

        updates = patch.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = await repo.update(threshold_id, updates)
        return await _threshold_response(conn, scope, updated)


@router.delete(
    "/rules/{rule_id}/thresholds/{scope}/{threshold_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a threshold",
    description="Removes a threshold override from a rule.",
    responses={
        404: {"model": ErrorMessage, "description": "Rule or threshold not found"},
        400: {"model": ErrorMessage, "description": "Invalid scope"},
        **COMMON_RESPONSES,
    },
)
async def delete_threshold(rule_id: int, scope: str, threshold_id: int):
    _validate_scope(scope)

    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        if not await rule_repo.find_by_id(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        repo = threshold_repository(scope, conn)
        row = await repo.find_by_id(threshold_id)
        if not row or row.rule_id != rule_id:
            raise HTTPException(status_code=404, detail="Threshold not found")

        await repo.delete(threshold_id)
        return None


def _channel_response(channel) -> ChannelResponse:
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        enabled=channel.enabled,
        has_credentials=bool(channel.credentials),
    )


@router.get(
    "/channels",
    response_model=List[ChannelResponse],
    summary="List notification channels",
    description="Returns all notifier channels. Credentials are never exposed, only whether they are set.",
    responses={**COMMON_RESPONSES},
)
async def list_channels():
    async with DatabaseConnection() as conn:
        channel_repo = NotifierChannelRepository(conn)
        channels = await channel_repo.find_all()
        return [_channel_response(channel) for channel in channels]


@router.patch(
    "/channels/{channel_id}",
    response_model=ChannelResponse,
    summary="Configure a notification channel",
    description="Updates the enabled flag and/or the channel credentials. Credentials are stored encrypted.",
    responses={
        404: {"model": ErrorMessage, "description": "Channel not found"},
        400: {"model": ErrorMessage, "description": "No fields to update"},
        **COMMON_RESPONSES,
    },
)
async def patch_channel(channel_id: int, patch: ChannelPatch):
    async with DatabaseConnection() as conn:
        channel_repo = NotifierChannelRepository(conn)
        channel = await channel_repo.find_by_id(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Channel not found")

        updates = patch.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        if "credentials" in updates:
            updates["credentials"] = encrypt(json.dumps(updates["credentials"]))

        updated = await channel_repo.update(channel_id, updates)
        return _channel_response(updated)
