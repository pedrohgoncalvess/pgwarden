from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.auth.services import get_current_user
from app.common.models import COMMON_RESPONSES, ErrorMessage
from app.databases.docs.models import (
    ColumnDocPut,
    ColumnDocResponse,
    DatabaseDocPut,
    DatabaseDocResponse,
    IndexDocPut,
    IndexDocResponse,
    SchemaDocPut,
    SchemaDocResponse,
    TableDocPut,
    TableDocResponse,
)
from app.databases.docs import services
from database.connection import DatabaseConnection
from database.models.base import User


router = APIRouter(
    prefix="/databases/{database_id}/docs",
    tags=["docs"],
)


@router.get(
    "",
    response_model=DatabaseDocResponse,
    summary="Get database documentation",
    responses={404: {"model": ErrorMessage, "description": "Documentation not found"}, **COMMON_RESPONSES},
)
async def get_database_documentation(database_id: UUID, _current_user: User = Depends(get_current_user)):
    async with DatabaseConnection() as conn:
        return await services.get_database_doc(conn, database_id)


@router.put(
    "",
    response_model=DatabaseDocResponse,
    status_code=status.HTTP_200_OK,
    summary="Save database documentation",
    responses={**COMMON_RESPONSES},
)
async def put_database_documentation(
    database_id: UUID,
    doc_in: DatabaseDocPut,
    current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.put_database_doc(conn, database_id, doc_in, current_user.id)


@router.get(
    "/schemas/{schema_name}",
    response_model=SchemaDocResponse,
    summary="Get schema documentation",
    responses={404: {"model": ErrorMessage, "description": "Documentation not found"}, **COMMON_RESPONSES},
)
async def get_schema_documentation(
    database_id: UUID,
    schema_name: str,
    _current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.get_schema_doc(conn, database_id, schema_name)


@router.put(
    "/schemas/{schema_name}",
    response_model=SchemaDocResponse,
    status_code=status.HTTP_200_OK,
    summary="Save schema documentation",
    responses={**COMMON_RESPONSES},
)
async def put_schema_documentation(
    database_id: UUID,
    schema_name: str,
    doc_in: SchemaDocPut,
    current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.put_schema_doc(conn, database_id, schema_name, doc_in, current_user.id)


@router.get(
    "/tables/{table_id}",
    response_model=TableDocResponse,
    summary="Get table documentation",
    responses={404: {"model": ErrorMessage, "description": "Documentation not found"}, **COMMON_RESPONSES},
)
async def get_table_documentation(
    database_id: UUID,
    table_id: UUID,
    _current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.get_table_doc(conn, database_id, table_id)


@router.put(
    "/tables/{table_id}",
    response_model=TableDocResponse,
    status_code=status.HTTP_200_OK,
    summary="Save table documentation",
    responses={**COMMON_RESPONSES},
)
async def put_table_documentation(
    database_id: UUID,
    table_id: UUID,
    doc_in: TableDocPut,
    current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.put_table_doc(conn, database_id, table_id, doc_in, current_user.id)


@router.get(
    "/columns/{column_id}",
    response_model=ColumnDocResponse,
    summary="Get column documentation",
    responses={404: {"model": ErrorMessage, "description": "Documentation not found"}, **COMMON_RESPONSES},
)
async def get_column_documentation(
    database_id: UUID,
    column_id: UUID,
    _current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.get_column_doc(conn, database_id, column_id)


@router.put(
    "/columns/{column_id}",
    response_model=ColumnDocResponse,
    status_code=status.HTTP_200_OK,
    summary="Save column documentation",
    responses={**COMMON_RESPONSES},
)
async def put_column_documentation(
    database_id: UUID,
    column_id: UUID,
    doc_in: ColumnDocPut,
    current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.put_column_doc(conn, database_id, column_id, doc_in, current_user.id)


@router.get(
    "/indexes/{index_id}",
    response_model=IndexDocResponse,
    summary="Get index documentation",
    responses={404: {"model": ErrorMessage, "description": "Documentation not found"}, **COMMON_RESPONSES},
)
async def get_index_documentation(
    database_id: UUID,
    index_id: UUID,
    _current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.get_index_doc(conn, database_id, index_id)


@router.put(
    "/indexes/{index_id}",
    response_model=IndexDocResponse,
    status_code=status.HTTP_200_OK,
    summary="Save index documentation",
    responses={**COMMON_RESPONSES},
)
async def put_index_documentation(
    database_id: UUID,
    index_id: UUID,
    doc_in: IndexDocPut,
    current_user: User = Depends(get_current_user),
):
    async with DatabaseConnection() as conn:
        return await services.put_index_doc(conn, database_id, index_id, doc_in, current_user.id)
