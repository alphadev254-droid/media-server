from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from ..core.config import settings

router = APIRouter(tags=["metrics"])

@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(x_metrics_token: str = Header(...)):
    if x_metrics_token != settings.metrics_token:
        raise HTTPException(403, "Forbidden")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
