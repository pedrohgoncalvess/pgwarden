"""Register the application routes in one place."""

from fastapi import FastAPI, Depends
from app.access.services import authorize_request
from app.access.router import router as access_router
from app.access.catalog import router as catalog_router

from app.auth.router import router as auth_router
from app.auth.passwords import router as passwords_router
from app.databases.schemas.router import router as schema_router
from app.databases.schemas.history.router import router as schema_history_router
from app.databases.router import router as database_router
from app.servers.router import router as server_router
from app.databases.sessions.router import router as sessions_router
from app.databases.locks.router import router as locks_router
from app.databases.configs.router import router as db_config_router
from app.databases.runs.router import router as db_runs_router
from app.databases.metrics.router import router as db_metrics_router
from app.databases.native_queries.router import router as db_native_queries_router
from app.databases.analytics.router import router as db_analytics_router
from app.databases.analytics.query.router import router as query_analytics_router
from app.databases.analytics.server_metrics_router import (
    router as server_metrics_analytics_router,
)
from app.databases.analytics.table_usage_router import router as table_usage_router
from app.databases.analytics.recommendations_router import (
    router as recommendations_router,
)
from app.servers.configs.router import router as srv_config_router
from app.servers.runs.router import router as srv_runs_router
from app.servers.metrics.router import router as srv_metrics_router
from app.tags.router import router as tags_router
from app.databases.docs.router import router as docs_router
from app.metadata.search.router import router as metadata_search_router
from app.notifier.router import router as notifier_router
from app.notifications.router import router as notifications_router
from app.health.router import router as health_router
from app.services.router import router as services_router
from app.projects.router import router as projects_router
from app.ingestion.router import router as ingestion_router
from app.retention.router import router as retention_router


def register_routes(app: FastAPI) -> None:
    """Attach administration, monitoring, and ingestion endpoints."""
    app.include_router(auth_router, prefix="/v1")
    app.include_router(passwords_router, prefix="/v1")
    app.include_router(catalog_router, prefix="/v1")
    app.include_router(schema_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(schema_history_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(database_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(server_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(sessions_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(locks_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(db_config_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(db_runs_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(db_metrics_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(db_native_queries_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(db_analytics_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(query_analytics_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(server_metrics_analytics_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(table_usage_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(recommendations_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(srv_config_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(srv_runs_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(srv_metrics_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(tags_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(docs_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(metadata_search_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(notifier_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(notifications_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(health_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(services_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(projects_router, prefix="/v1", dependencies=[Depends(authorize_request)])
    app.include_router(ingestion_router, prefix="/v1")
    app.include_router(retention_router, prefix="/v1")

    app.include_router(access_router, prefix="/v1", dependencies=[Depends(authorize_request)])
