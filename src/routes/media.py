from fastapi import APIRouter, Depends
from ..core.security import verify_api_key
from ..services.storage import get_signed_url

router = APIRouter(prefix="/media", tags=["media"])

@router.get("/signed/{bucket}/{key}")
async def signed_url(
    bucket: str, key: str,
    expires: int = 3600,
    _: str = Depends(verify_api_key),
):
    url = await get_signed_url(bucket, key, expires)
    return {"url": url, "expires_in": expires}
