"""The API error envelope and its exception handlers.

The frontend contract (Sensei-AI/docs/FASTAPI_INTEGRATION.md) requires every
non-2xx response to be a JSON object of the form::

    { "error": { "code": "invalid_credentials", "message": "…", "details": {} } }

with status codes ``400``/``401``/``403``/``404``/``409``/``413``/``422``/``429``
/``500``. :class:`ApiError` is the exception routers raise for domain failures;
the handlers below translate FastAPI's own exceptions (unknown routes, request
validation, unhandled errors) into the same envelope so the client never sees a
raw HTTP error body.

Mapping status → code follows the contract's error list; the ``details`` object
carries structured context (e.g. validation field errors) and defaults to ``{}``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS_TO_CODE: dict[int, str] = {
    400: "invalid_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}


def error_envelope(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a response body in the contract's error shape."""
    return {"error": {"code": code, "message": message, "details": details or {}}}


class ApiError(Exception):
    """A domain error that becomes a contract-shaped error response.

    Args:
        status_code: HTTP status for the response (default ``400``).
        code: Stable machine-readable code from ``STATUS_TO_CODE`` (or a more
            specific one such as ``invalid_credentials``).
        message: Human-readable message.
        details: Optional structured context for the client.
    """

    def __init__(
        self,
        status_code: int = 400,
        code: str | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code or STATUS_TO_CODE.get(status_code, "internal_error")
        self.message = message
        self.details = details


def register_exception_handlers(app: FastAPI) -> None:
    """Attach envelope-producing handlers to ``app``.

    Safe to call from the app factory and from tests that build throwaway apps.
    """

    @app.exception_handler(ApiError)
    async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = STATUS_TO_CODE.get(exc.status_code, "internal_error")
        message = str(exc.detail) or code
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(code, message),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = {"errors": exc.errors()}
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                "validation_error", "Request failed validation", details
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        # The exception is swallowed deliberately so the client always receives
        # the contract envelope; the server logs it via FastAPI's own machinery.
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                "internal_error",
                f"Internal server error: {type(exc).__name__}",
            ),
        )
