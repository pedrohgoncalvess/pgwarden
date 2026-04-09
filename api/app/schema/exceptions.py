class BaseAppException(Exception):
    def __init__(self, message: str, status_code: int = 500, details: str = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class DatabaseNotFoundError(BaseAppException):
    def __init__(self, database_id: str):
        super().__init__(
            message="Database not found.",
            status_code=404,
            details=f"No matching active database found for ID: {database_id}"
        )


class SchemaFetchError(BaseAppException):
    def __init__(self, details: str):
        super().__init__(
            message="Failed to fetch schema.",
            status_code=500,
            details=details
        )
