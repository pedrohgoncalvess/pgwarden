from pydantic import BaseModel
from typing import Any, Optional

class ErrorMessage(BaseModel):
    detail: str

class ExceptionResponse(BaseModel):
    message: str
    details: Optional[Any] = None

COMMON_RESPONSES = {
    401: {"model": ErrorMessage, "description": "Unauthorized - Missing or invalid credentials"},
    403: {"model": ErrorMessage, "description": "Forbidden - Insufficient permissions"},
    500: {"model": ExceptionResponse, "description": "Internal Server Error"},
}
