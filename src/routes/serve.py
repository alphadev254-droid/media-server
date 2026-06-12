from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from ..core.config import settings

router = APIRouter(tags=["serve"])


@router.get("/media-images/{key}")
async def serve_media_image(key: str, request: Request):
    """Serve media files publicly via redirect to MinIO.
    
    Checks the Origin header against ALLOWED_ORIGINS from env.
    """
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    
    # Allow requests with no origin (direct browser hits, curl, etc.)
    # Only block if origin is explicitly set and not allowed
    if origin:
        if origin not in settings.allowed_origins:
            # Also check if referer starts with any allowed origin
            if not any(referer.startswith(allowed) for allowed in settings.allowed_origins if referer):
                raise HTTPException(
                    status_code=403,
                    detail=f"Origin not allowed: {origin}"
                )
    
    url = f"{settings.minio_endpoint}/media-images/{key}"
    return RedirectResponse(url=url)
