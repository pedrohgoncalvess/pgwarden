from app.databases.schemas.exceptions import BaseAppException


class HistoryDatabaseNotFoundError(BaseAppException):
    def __init__(self, database_id: str):
        super().__init__(
            message=f"Database {database_id} not found",
            status_code=404,
            details=f"No matching active database found for ID: {database_id}"
        )


class HistoryFetchError(BaseAppException):
    def __init__(self, details: str):
        super().__init__(
            message="Failed to fetch schema history.",
            status_code=500,
            details=details
        )
