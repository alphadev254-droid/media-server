import io
import magic
from PIL import Image, ImageOps
from ..core.config import ALLOWED_MIMES, MAX_FILE_SIZE
from fastapi import HTTPException

def validate_file(data: bytes, declared_mime: str) -> str:
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large")
    real_mime = magic.from_buffer(data[:2048], mime=True)
    if real_mime not in ALLOWED_MIMES:
        raise HTTPException(415, f"File type not allowed: {real_mime}")
    return real_mime

def process_image(data: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((4000, 4000), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
        return out.getvalue(), "image/webp"
    except Exception as e:
        raise HTTPException(422, f"Could not process image: {e}")

def get_extension(mime: str, original_name: str) -> str:
    mapping = {
        "image/webp": "webp", "image/jpeg": "jpg", "image/png": "png",
        "image/gif": "gif", "video/mp4": "mp4", "video/webm": "webm",
        "audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg",
        "application/pdf": "pdf",
    }
    return mapping.get(mime, original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin")
