from __future__ import annotations

"""FastAPI application entrypoint."""

import importlib
import logging
import pkgutil

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppException
from app.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _include_api_routers(app: FastAPI) -> None:
    """Import and register all routers under app.api.v1.endpoints."""
    try:
        endpoints_package = importlib.import_module("app.api.v1.endpoints")
    except ImportError:
        logger.warning("API endpoints package not found; skipping router registration")
        return

    for module_info in pkgutil.iter_modules(endpoints_package.__path__):
        if module_info.name.startswith("_"):
            continue
        module_name = f"{endpoints_package.__name__}.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.exception("Failed to import router module '%s'", module_name)
            continue

        router = getattr(module, "router", None)
        if router is None:
            logger.debug("Skipping module '%s'; no router attribute found", module_name)
            continue

        app.include_router(router, prefix=settings.API_V1_STR)
        logger.info("Registered router from %s", module_name)


def _configure_cors(app: FastAPI) -> None:
    """Attach CORS middleware using configured origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_application() -> FastAPI:
    """Application factory used by ASGI servers and tests."""
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        version="1.0.0",
    )

    _configure_cors(app)
    _include_api_routers(app)

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("Starting %s in %s mode", settings.PROJECT_NAME, settings.ENVIRONMENT)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Shutting down %s", settings.PROJECT_NAME)
        await engine.dispose()

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Basic health check endpoint."""
        return {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "environment": settings.ENVIRONMENT,
        }

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "request_validation_error",
                    "message": "Request validation failed",
                    # jsonable_encoder decodes any bytes in the error context (e.g. raw
                    # form/body input) that json.dumps would otherwise choke on.
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        message = str(exc) if settings.DEBUG else "Internal server error"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "internal_server_error", "message": message}},
        )

    return app


app = create_application()
