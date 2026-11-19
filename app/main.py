from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Request

from config import get_settings
from pilot.domain.errors import install_error_handlers
from pilot.domain.services import create_services
from pilot.router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.pilot_transport not in {"fixture", "polza"}:
        raise RuntimeError("PILOT_TRANSPORT must be polza or fixture.")
    if settings.pilot_transport == "polza" and not settings.polza_api_key.strip():
        raise RuntimeError("POLZA_API_KEY is required in polza mode.")
    if len(settings.visitor_cookie_secret.strip()) < 32 or settings.visitor_cookie_secret == "local-development-only-change-me":
        raise RuntimeError("Set a local VISITOR_COOKIE_SECRET of at least 32 characters.")
    origins = frozenset(value.strip() for value in settings.allowed_browser_origins.split(",") if value.strip())
    if not origins or "*" in origins:
        raise RuntimeError("Configure explicit allowed browser origins.")
    storage_root = Path(settings.pilot_storage_root)
    storage_root.mkdir(parents=True, exist_ok=True)
    async with asyncpg.create_pool(settings.database_url, min_size=1, max_size=10) as pool:
        app.state.pilot_settings = settings
        app.state.pilot_origins = origins
        app.state.pilot_services = create_services(pool, storage_root, settings)
        app.state.pilot_pool = pool
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
install_error_handlers(app)
app.include_router(router, prefix="/api")


@app.get("/health", include_in_schema=False)
async def health(request: Request):
    await request.app.state.pilot_pool.fetchval("SELECT 1")
    return {"status": "ok"}
