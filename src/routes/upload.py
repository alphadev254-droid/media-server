from http.client import HTTPException

from fastapi import APIRouter, UploadFile, File, Depends, Header
from typing import Optional
import uuid
from ..core.config import bucket_for_mime, settings
from ..core.security import verify_api_key
from ..services.storage import upload_file, delete_file
from ..services.processor import validate_file, process_image, get_extension

router = APIRouter(prefix="/upload", tags=["upload"])

@router.post("/")
async def upload(
    file: UploadFile = File(...),
    x_client_id: Optional[str] = Header(None),
    x_media_base_url: Optional[str] = Header(None),
    _: str = Depends(verify_api_key),
):
    # Require base URL — no silent fallback
    if not x_media_base_url:
        raise HTTPException(400, "X-Media-Base-Url header is required")
    if x_media_base_url not in settings.allowed_media_base_urls:
        raise HTTPException(403, f"Media base URL not allowed: {x_media_base_url}")

    data = await file.read()
    real_mime = validate_file(data, file.content_type)
    if real_mime.startswith("image/") and real_mime != "image/gif":
        data, real_mime = process_image(data)
    ext    = get_extension(real_mime, file.filename)
    key    = f"{uuid.uuid4()}.{ext}"
    bucket = bucket_for_mime(real_mime)
    await upload_file(bucket, key, data, real_mime, {
        "original_name": file.filename,
        "client_id": x_client_id or "unknown",
    })

    return {
        "id": key, "bucket": bucket,
        "url": f"{x_media_base_url}/{bucket}/{key}",
        "size": len(data), "mime": real_mime,
    }



@router.delete("/{bucket}/{key}")
async def delete(bucket: str, key: str, _: str = Depends(verify_api_key)):
    await delete_file(bucket, key)
    return {"deleted": True}
