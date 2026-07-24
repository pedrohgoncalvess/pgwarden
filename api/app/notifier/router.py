from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from app.notifier.models import (
    RulePatch,
    RuleResponse,
    ThresholdPatch,
    ThresholdResponse,
)
from database.connection import DatabaseConnection
from database.operations.notifier import (
    NotifierRuleRepository,
    get_threshold_scope,
    threshold_repository,
)


router = APIRouter(
    prefix="/notifier/rules",
    tags=["notifier"],
    dependencies=[Depends(get_current_user)],
)


_SCOPE_ENTITY_ATTR = {
    "server": "server_id",
    "database": "database_id",
    "table": "table_id",
    "index": "index_id",
}


def _threshold_response(scope: str, row) -> ThresholdResponse:
    entity_attr = _SCOPE_ENTITY_ATTR[scope]
    return ThresholdResponse(
        id=row.id,
        rule_id=row.rule_id,
        scope=scope,
        type=row.type,
        entity_id=getattr(row, entity_attr),
        warning=row.warning,
        critical=row.critical,
        direction=row.direction,
    )


async def _load_thresholds(conn, rule_id: int) -> List[ThresholdResponse]:
    thresholds: List[ThresholdResponse] = []
    for scope in ("server", "database", "table", "index"):
        repo = threshold_repository(scope, conn)
        rows = await repo.find_by(rule_id=rule_id)
        thresholds.extend([_threshold_response(scope, row) for row in rows])
    return thresholds


@router.get(
    "",
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
            RuleResponse(
                **{k: getattr(rule, k) for k in rule.__dict__ if not k.startswith("_")},
                thresholds=await _load_thresholds(conn, rule.id),
            )
            for rule in rules
        ]


@router.get(
    "/{rule_id}",
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

        return RuleResponse(
            **{k: getattr(rule, k) for k in rule.__dict__ if not k.startswith("_")},
            thresholds=await _load_thresholds(conn, rule.id),
        )


@router.patch(
    "/{rule_id}",
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
        return RuleResponse(
            **{k: getattr(updated, k) for k in updated.__dict__ if not k.startswith("_")},
            thresholds=await _load_thresholds(conn, updated.id),
        )


@router.get(
    "/{rule_id}/thresholds/{scope}/{threshold_id}",
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
    try:
        get_threshold_scope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid threshold scope: {scope}")

    async with DatabaseConnection() as conn:
        rule_repo = NotifierRuleRepository(conn)
        if not await rule_repo.find_by_id(rule_id):
            raise HTTPException(status_code=404, detail="Rule not found")

        repo = threshold_repository(scope, conn)
        row = await repo.find_by_id(threshold_id)
        if not row or row.rule_id != rule_id:
            raise HTTPException(status_code=404, detail="Threshold not found")

        return _threshold_response(scope, row)


@router.patch(
    "/{rule_id}/thresholds/{scope}/{threshold_id}",
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
    try:
        get_threshold_scope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid threshold scope: {scope}")

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
        return _threshold_response(scope, updated)


@router.delete(
    "/{rule_id}/thresholds/{scope}/{threshold_id}",
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
    try:
        get_threshold_scope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid threshold scope: {scope}")

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
