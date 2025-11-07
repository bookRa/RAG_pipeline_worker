from fastapi import FastAPI

from .api.routers import router as pipeline_router
from .config import settings

app = FastAPI(title=settings.app_name)
app.include_router(pipeline_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
