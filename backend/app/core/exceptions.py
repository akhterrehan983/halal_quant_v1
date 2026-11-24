from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class HalalQuantError(Exception):
    """Domain error with optional HTTP status."""

    def __init__(self, message: str, status_code: int = 400, code: str = "domain_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


async def halal_quant_exception_handler(_: Request, exc: HalalQuantError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


class ConcurrentBookUpdate(HalalQuantError):
    """Optimistic concurrency failure on portfolio book persistence."""

    def __init__(self) -> None:
        super().__init__(
            "Portfolio book was modified concurrently; retry the operation",
            status_code=409,
            code="concurrent_book_update",
        )