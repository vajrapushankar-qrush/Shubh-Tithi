"""Shared API plumbing: DB session dependency and a consistent error shape."""
from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import SessionLocal


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def resolve_zone(tz_name: str) -> ZoneInfo:
    """Validate an IANA timezone name, raising a JSON 422 rather than a 500.

    ``zoneinfo`` raises ``ZoneInfoNotFoundError`` for an unknown key and
    ``ValueError`` for a structurally invalid one (an absolute path, a key
    containing ``..``). Neither is an :class:`ApiError`, so without this the
    request surfaces as a bare text/plain 500. A UTC *offset* such as
    ``+05:30`` is not an IANA key and lands here too -- the message says so
    explicitly, since that is the mistake consumers actually make.
    """
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
        raise ApiError(
            422,
            "invalid_timezone",
            f"Unknown IANA timezone: {tz_name!r}.",
            "Expected an IANA timezone name such as 'Asia/Kolkata'. "
            "UTC offsets ('+05:30') and abbreviations ('IST') are not accepted."
            f" ({type(exc).__name__})",
        ) from exc


def error_payload(code: str, message: str, detail: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail: str | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


def install_error_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(f"http_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_payload("validation_error", "Invalid request parameters.",
                                  str(exc.errors())),
        )

    import swisseph as swe

    @app.exception_handler(swe.Error)
    async def _ephemeris_error(request: Request, exc: swe.Error):
        """Swiss Ephemeris failures as JSON rather than a text/plain 500.

        The common case by far is a date outside the backend's range (the
        built-in Moshier model spans JD 625000.5..2818000.5, roughly 3001 BCE
        to 3000 CE), which is a bad *request*, not a server fault.
        """
        message = str(exc)
        if "outside" in message and "range" in message:
            return JSONResponse(
                status_code=422,
                content=error_payload(
                    "ephemeris_range",
                    "Date is outside the supported ephemeris range.",
                    message,
                ),
            )
        return JSONResponse(
            status_code=500,
            content=error_payload("ephemeris_error",
                                  "Ephemeris computation failed.", message),
        )
