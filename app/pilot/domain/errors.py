from dataclasses import dataclass
from fastapi import FastAPI
from fastapi.responses import JSONResponse


@dataclass
class DomainError(Exception):
    http_status: int
    code: str
    message: str
    current_revision: int | None = None

    def to_response(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "current_revision": self.current_revision,
            }
        }


def install_error_handlers(app: FastAPI):
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def request_invalid(request, error):
        return JSONResponse(
            DomainError(
                422, "invalid_input", "Некорректные данные запроса."
            ).to_response(),
            status_code=422,
        )

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse(error.to_response(), status_code=error.http_status)


def invalid(message="Недопустимое действие.", code="invalid_state", revision=None):
    raise DomainError(409, code, message, revision)


def not_found():
    raise DomainError(404, "not_found", "Материал не найден.")
