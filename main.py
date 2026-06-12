from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from src.core.config import settings
from src.core.logging import setup_logging, logger
from src.core.security import cors_middleware_config
from src.services.storage import ensure_buckets
from src.routes import upload, media, metrics, serve

setup_logging()

app = FastAPI(title="Media Server", version="1.0.0")

# CORS — restrict to allowed origins only
app.add_middleware(CORSMiddleware, **cors_middleware_config())

# Auto Prometheus metrics on all routes
Instrumentator().instrument(app).expose(app, endpoint="/_internal/metrics")

app.include_router(upload.router)
app.include_router(media.router)
app.include_router(metrics.router)
app.include_router(serve.router)

@app.on_event("startup")
async def startup():
    ensure_buckets()
    logger.info("media_server_started", port=settings.port)

@app.get("/health")
async def health():
    return {"status": "ok"}
