from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.dashboard import router as dashboard_router
from .api.routers import router as pipeline_router
from .api.batch_routers import router as batch_router
from .api.batch_dashboard import router as batch_dashboard_router
from .config import settings
from .observability.logging_setup import setup_logging

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Configure logging from settings (LOG_LEVEL in .env)
# This is the SINGLE source of truth for log level configuration
setup_logging()

app = FastAPI(title=settings.app_name)
app.include_router(pipeline_router)
app.include_router(dashboard_router)
app.include_router(batch_router)
app.include_router(batch_dashboard_router)

static_directory = BASE_DIR / "static"
if static_directory.exists():
    app.mount("/static", StaticFiles(directory=str(static_directory)), name="static")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
