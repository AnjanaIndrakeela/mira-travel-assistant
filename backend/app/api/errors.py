"""One error shape for every failure (step 9.9): {"error": code, "message": friendly text}.

No stack trace, exception text or request body is ever returned (a booking request holds a
card number, so validation errors name the fields, never their values).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("mira.api")

CODES = {400: "bad_request", 401: "unauthorised", 403: "forbidden", 404: "not_found",
         405: "method_not_allowed", 409: "conflict", 422: "invalid_request", 429: "too_many_requests", 500: "internal_error"}
INTERNAL = ("Something went wrong on our side. Please try again in a moment, or leave your "
            "details and a travel specialist will get back to you.")


def _error(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": CODES.get(status, "error"),
                                                     "message": message, **extra})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "That request didn't work."
        if exc.status_code == 404 and message == "Not Found":
            message = "We couldn't find that."
        return _error(exc.status_code, message)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
        return _error(422, "Some details are missing or not valid: " + ", ".join(fields) + ".",
                      fields=fields)

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception):
        logger.error("unhandled %s on %s %s", exc.__class__.__name__, request.method, request.url.path)
        return _error(500, INTERNAL)
