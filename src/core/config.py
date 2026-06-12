from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    minio_endpoint: str = "http://127.0.0.1:9000"
    minio_access_key: str = "admin"
    minio_secret_key: str = "password"
    minio_secure: bool = False
    port: int = 3010
    workers: int = 2
    media_base_url: str = "https://media.yourdomain.com"
    api_key: str = "changeme"
    allowed_origins: List[str] = []
    allowed_media_base_urls: List[str] = []  # ← add this
    metrics_token: str = "changeme"

    class Config:
        env_file = ".env"

settings = Settings()

BUCKETS = {
    "image":    "media-images",
    "video":    "media-videos",
    "audio":    "media-audio",
    "document": "media-documents",
}

ALLOWED_MIMES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "video/mp4", "video/quicktime", "video/x-mkvideo", "video/webm",
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/aac",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_FILE_SIZE = 500 * 1024 * 1024

def bucket_for_mime(mime: str) -> str:
    if mime.startswith("image/"): return BUCKETS["image"]
    if mime.startswith("video/"): return BUCKETS["video"]
    if mime.startswith("audio/"): return BUCKETS["audio"]
    return BUCKETS["document"]
