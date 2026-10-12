"""One error shape for the whole API: {"error": {"code", "message", "request_id"}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_logger, get_request_id, log_event

logger = get_logger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers


def error_response(code: str, message: str, status_code: int, headers: dict[str, str] | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": get_request_id()}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        log_event(logger, "request_error", code=exc.code, status=exc.status_code, message=exc.message)
        return error_response(exc.code, exc.message, exc.status_code, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"{where}: {first.get('msg', 'invalid request')}" if where else first.get("msg", "invalid request")
        return error_response("VALIDATION_ERROR", message, 422)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(code, str(exc.detail), exc.status_code)

    # Unexpected exceptions become a 500 in the request middleware (app/main.py).
