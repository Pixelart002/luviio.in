"""
Image Service — Supabase Storage
=================================
Architecture Layer: Services (Domain Logic)
Path: app/services/image.py
"""
import io
import logging
import uuid
from typing import Optional
from PIL import Image, UnidentifiedImageError

# 🔥 ARCHITECTURE CHANGE: Corrected Import
from app.core.supabase import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FILE_BYTES = 5 * 1024 * 1024
THUMB_SIZE = (800, 800)
SMALL_SIZE = (200, 200)
WEBP_QUALITY = 80
WEBP_QUALITY_SMALL = 60
STORAGE_BUCKET = "product-images"

_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
_IMAGE_MAGIC: dict[bytes, str] = {b"\xff\xd8\xff": "jpeg", b"\x89PNG": "png", b"GIF8": "gif", b"RIFF": "webp"}

def _validate_image(file_bytes: bytes, filename: str = "unknown") -> None:
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError(f"Image '{filename}' exceeds {MAX_FILE_BYTES // (1024*1024)} MB limit")
    if len(file_bytes) < 100:
        raise ValueError(f"Image '{filename}' is too small — likely corrupted")
    if not any(file_bytes.startswith(magic) for magic in _IMAGE_MAGIC):
        raise ValueError(f"'{filename}' is not a valid image format. Accepted: JPEG, PNG, WebP, GIF")

def _process_image(file_bytes: bytes, size: tuple[int, int] = THUMB_SIZE, quality: int = WEBP_QUALITY) -> bytes:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P": img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"): background.paste(img, mask=img.split()[-1])
            else: background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        if img.width * img.height > Image.MAX_IMAGE_PIXELS: raise ValueError(f"Image dimensions too large")
        img.thumbnail(size, _LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality, optimize=True)
        return buffer.getvalue()
    except UnidentifiedImageError:
        raise ValueError("Invalid image file format. Please upload JPEG, PNG, or WebP.")
    except ValueError: raise
    except Exception as exc:
        raise ValueError(f"Could not process image: {str(exc)[:100]}")

def _upload_to_storage(file_bytes: bytes, path: str, content_type: str = "image/webp") -> str:
    sb = get_admin_supabase()
    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            path, file_bytes, {"content-type": content_type, "upsert": "true", "cache-control": "public, max-age=31536000, immutable"}
        )
        url = sb.storage.from_(STORAGE_BUCKET).get_public_url(path)
        return url.split("?")[0].rstrip("?")
    except Exception as exc:
        raise RuntimeError("Failed to upload image to cloud storage. Please try again.")

def _delete_from_storage(path: str) -> None:
    try:
        sb = get_admin_supabase()
        sb.storage.from_(STORAGE_BUCKET).remove([path])
    except Exception as exc:
        logger.warning("Storage delete failed (non-critical) | path=%s: %s", path, exc)

def upload_product_image(file_bytes: bytes, product_id: str, *, filename: str = "unknown", generate_thumbnail: bool = True) -> str:
    _validate_image(file_bytes, filename)
    optimized = _process_image(file_bytes, size=THUMB_SIZE, quality=WEBP_QUALITY)
    unique_id = uuid.uuid4().hex[:12]
    main_path = f"products/{product_id}/{unique_id}.webp"
    url = _upload_to_storage(optimized, main_path)
    
    if generate_thumbnail:
        try:
            thumbnail = _process_image(file_bytes, size=SMALL_SIZE, quality=WEBP_QUALITY_SMALL)
            thumb_path = f"products/{product_id}/{unique_id}_thumb.webp"
            _upload_to_storage(thumbnail, thumb_path)
        except Exception as exc:
            logger.warning("Thumbnail generation failed for product %s: %s", product_id[:8], exc)
    return url

def upload_multiple_images(files: list[tuple[bytes, str]], product_id: str, *, max_images: int = 10) -> list[str]:
    if len(files) > max_images: raise ValueError(f"Maximum {max_images} images allowed")
    urls, errors = [], []
    for i, (file_bytes, filename) in enumerate(files):
        try: urls.append(upload_product_image(file_bytes, product_id, filename=filename))
        except Exception as exc: errors.append(f"Image {i+1} ('{filename}'): {exc}")
    
    if errors:
        for url in urls:
            try:
                path = url.split(f"/{STORAGE_BUCKET}/")[1] if f"/{STORAGE_BUCKET}/" in url else None
                if path: _delete_from_storage(path)
            except Exception as cleanup_error:
                logger.warning("Image rollback cleanup failed: %s", cleanup_error)
        raise ValueError(f"Failed to upload {len(errors)} image(s): {'; '.join(errors)}")
    return urls

def delete_product_image(url: str) -> None:
    if f"/{STORAGE_BUCKET}/" not in url: return
    path = url.split(f"/{STORAGE_BUCKET}/")[1]
    _delete_from_storage(path)

def delete_all_product_images(product_id: str) -> int:
    sb = get_admin_supabase()
    prefix = f"products/{product_id}/"
    try:
        files = sb.storage.from_(STORAGE_BUCKET).list(prefix)
        if not files: return 0
        paths = [f"{prefix}{f['name']}" for f in files if isinstance(f, dict) and f.get('name') and f['name'] != ".emptyFolderPlaceholder"]
        if paths:
            sb.storage.from_(STORAGE_BUCKET).remove(paths)
            return len(paths)
    except Exception as exc:
        logger.error("Bulk image deletion failed for product %s: %s", product_id[:8], exc, exc_info=True)
    return 0
