"""
Image Service — Supabase Storage
=================================
Handles product image processing and upload to Supabase Storage.

Features:
  • WebP conversion with quality optimization
  • Automatic thumbnail generation (multiple sizes)
  • Magic byte validation (content-type spoof protection)
  • File size limits enforcement
  • Old image cleanup on re-upload
  • Structured logging with file sizes
  • Alpha channel (transparency) safe conversion to white background

Usage:
  from app.services.image import upload_product_image
  
  url = upload_product_image(file_bytes, product_id)
  # Returns: https://xxx.supabase.co/storage/v1/object/public/product-images/products/{id}.webp
"""
import io
import logging
import uuid
from typing import Optional

from PIL import Image, UnidentifiedImageError

from app.supabase_client import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FILE_BYTES = 5 * 1024 * 1024      # 5 MB
THUMB_SIZE = (800, 800)                # Main image
SMALL_SIZE = (200, 200)                # Thumbnail for listings
WEBP_QUALITY = 80                      # 0-100 (80 = good balance)
WEBP_QUALITY_SMALL = 60                # Lower quality for thumbnails
STORAGE_BUCKET = "product-images"

# Safe Resampling for all Pillow versions
_LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

# Magic bytes for supported formats
_IMAGE_MAGIC: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",
}


# ══════════════════════════════════════════════════════════════════════════════
#  VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def _validate_image(file_bytes: bytes, filename: str = "unknown") -> None:
    """
    Validate image before processing.
    Checks: file size, magic bytes, dimensions.
    """
    # Size check
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError(
            f"Image '{filename}' exceeds {MAX_FILE_BYTES // (1024*1024)} MB limit "
            f"(actual: {len(file_bytes) // 1024} KB)"
        )
    
    if len(file_bytes) < 100:
        raise ValueError(f"Image '{filename}' is too small — likely corrupted")
    
    # Magic byte check (prevent content-type spoofing)
    if not any(file_bytes.startswith(magic) for magic in _IMAGE_MAGIC):
        raise ValueError(
            f"'{filename}' is not a valid image format. "
            f"Accepted: JPEG, PNG, WebP, GIF"
        )


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def _process_image(
    file_bytes: bytes,
    size: tuple[int, int] = THUMB_SIZE,
    quality: int = WEBP_QUALITY,
) -> bytes:
    """
    Process raw image bytes → resize → WebP.
    Returns optimized bytes ready for upload.
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))
        
        # Convert to RGB (handles RGBA, P, etc.) with White Background
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # Check dimensions before resize
        if img.width * img.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError(f"Image dimensions too large: {img.width}x{img.height}")
        
        # Resize maintaining aspect ratio
        img.thumbnail(size, _LANCZOS)
        
        # Save as WebP
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality, optimize=True)
        optimized = buffer.getvalue()
        
        logger.debug(
            "Image processed | original=%dKB optimized=%dKB size=%dx%d",
            len(file_bytes) // 1024, len(optimized) // 1024,
            img.width, img.height
        )
        
        return optimized
        
    except UnidentifiedImageError:
        logger.error("Cannot identify image format — invalid/corrupted file")
        raise ValueError("Invalid image file format. Please upload JPEG, PNG, or WebP.")
    except ValueError:
        raise
    except Exception as exc:
        logger.error("Image processing failed: %s", exc, exc_info=True)
        raise ValueError(f"Could not process image: {str(exc)[:100]}")


# ══════════════════════════════════════════════════════════════════════════════
#  SUPABASE UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

def _upload_to_storage(
    file_bytes: bytes,
    path: str,
    content_type: str = "image/webp",
) -> str:
    """
    Upload bytes to Supabase Storage.
    Returns clean public URL.
    """
    sb = get_admin_supabase()
    
    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            path,
            file_bytes,
            {
                "content-type": content_type,
                "upsert": "true",
                "cache-control": "public, max-age=31536000, immutable",  # 1 year cache
            },
        )
        
        url = sb.storage.from_(STORAGE_BUCKET).get_public_url(path)
        
        # Clean URL (remove trailing query params)
        url = url.split("?")[0].rstrip("?")
        
        logger.info("Uploaded to storage | path=%s size=%dKB", path, len(file_bytes) // 1024)
        return url
        
    except Exception as exc:
        logger.error("Supabase upload failed | path=%s: %s", path, exc)
        raise RuntimeError("Failed to upload image to cloud storage. Please try again.")


def _delete_from_storage(path: str) -> None:
    """
    Delete file from Supabase Storage by path.
    Non-critical — logs warning on failure.
    """
    try:
        sb = get_admin_supabase()
        sb.storage.from_(STORAGE_BUCKET).remove([path])
        logger.info("Deleted from storage | path=%s", path)
    except Exception as exc:
        logger.warning("Storage delete failed (non-critical) | path=%s: %s", path, exc)


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def upload_product_image(
    file_bytes: bytes,
    product_id: str,
    *,
    filename: str = "unknown",
    generate_thumbnail: bool = True,
) -> str:
    """
    Process and upload a product image to Supabase Storage.
    
    Args:
        file_bytes: Raw image bytes
        product_id: UUID of the product
        filename: Original filename (for error messages)
        generate_thumbnail: Also generate a small thumbnail
    
    Returns:
        Public URL of the main (800x800) image
    
    Raises:
        ValueError: Invalid image format or size
        RuntimeError: Upload failed
    """
    # ── Validate ──────────────────────────────────────────────────────────────
    _validate_image(file_bytes, filename)
    
    # ── Process main image ────────────────────────────────────────────────────
    optimized = _process_image(file_bytes, size=THUMB_SIZE, quality=WEBP_QUALITY)
    
    # ── Generate unique filename ──────────────────────────────────────────────
    unique_id = uuid.uuid4().hex[:12]
    main_path = f"products/{product_id}/{unique_id}.webp"
    
    # ── Upload main image ─────────────────────────────────────────────────────
    url = _upload_to_storage(optimized, main_path)
    
    # ── Generate thumbnail (optional) ─────────────────────────────────────────
    if generate_thumbnail:
        try:
            thumbnail = _process_image(file_bytes, size=SMALL_SIZE, quality=WEBP_QUALITY_SMALL)
            thumb_path = f"products/{product_id}/{unique_id}_thumb.webp"
            _upload_to_storage(thumbnail, thumb_path)
        except Exception as exc:
            logger.warning("Thumbnail generation failed (non-critical): %s", exc)
    
    logger.info(
        "Product image uploaded | product=%s path=%s size=%dKB",
        product_id, main_path, len(optimized) // 1024
    )
    
    return url


def upload_multiple_images(
    files: list[tuple[bytes, str]],
    product_id: str,
    *,
    max_images: int = 10,
) -> list[str]:
    """
    Upload multiple product images.
    
    Args:
        files: List of (file_bytes, filename) tuples
        product_id: UUID of the product
        max_images: Maximum number of images allowed
    
    Returns:
        List of public URLs
    """
    if len(files) > max_images:
        raise ValueError(f"Maximum {max_images} images allowed (received: {len(files)})")
    
    urls = []
    errors = []
    
    for i, (file_bytes, filename) in enumerate(files):
        try:
            url = upload_product_image(file_bytes, product_id, filename=filename)
            urls.append(url)
        except (ValueError, RuntimeError) as exc:
            errors.append(f"Image {i+1} ('{filename}'): {exc}")
    
    if errors:
        # Cleanup already uploaded images on partial failure
        for url in urls:
            try:
                path = url.split(f"/{STORAGE_BUCKET}/")[1] if f"/{STORAGE_BUCKET}/" in url else None
                if path:
                    _delete_from_storage(path)
            except Exception:
                pass
        raise ValueError(f"Failed to upload {len(errors)} image(s): {'; '.join(errors)}")
    
    return urls


def delete_product_image(url: str) -> None:
    """
    Delete a product image from storage by its public URL.
    
    Args:
        url: Full public URL of the image to delete
    """
    if f"/{STORAGE_BUCKET}/" not in url:
        logger.warning("Cannot delete — URL not from our bucket: %s", url[:80])
        return
    
    path = url.split(f"/{STORAGE_BUCKET}/")[1]
    _delete_from_storage(path)


def delete_all_product_images(product_id: str) -> int:
    """
    Delete all images for a product.
    Returns count of deleted files.
    """
    sb = get_admin_supabase()
    prefix = f"products/{product_id}/"
    
    try:
        # List all files with this prefix
        files = sb.storage.from_(STORAGE_BUCKET).list(prefix)
        if not files:
            return 0
        
        # Parse names properly and ignore hidden empty placeholders
        paths = [
            f"{prefix}{f['name']}" for f in files 
            if isinstance(f, dict) and f.get('name') and f['name'] != ".emptyFolderPlaceholder"
        ]
        
        if paths:
            sb.storage.from_(STORAGE_BUCKET).remove(paths)
            logger.info("Deleted %d images | product=%s", len(paths), product_id)
            return len(paths)
    except Exception as exc:
        logger.warning("Batch delete failed | product=%s: %s", product_id, exc)
    
    return 0
