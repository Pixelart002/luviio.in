import io
import logging

from PIL import Image, UnidentifiedImageError

from app.supabase_client import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)


def upload_product_image(file_bytes: bytes, product_id: str) -> str:
    """
    Processes and uploads a product image to Supabase Storage.
    Returns the public URL of the uploaded image.
    """
    # ── 1. Safe Image Processing ──────────────────────────────────────────────
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=80)
        optimized = buffer.getvalue()
        
    except UnidentifiedImageError:
        logger.error("Failed to identify image for product %s. Invalid file.", product_id)
        raise ValueError("Invalid image file format.")
    except Exception as e:
        logger.error("PIL processing failed for product %s: %s", product_id, e)
        raise ValueError("Could not process the image.")

    # ── 2. Safe Supabase Upload ───────────────────────────────────────────────
    sb = get_admin_supabase()
    path = f"products/{product_id}.webp"
    
    try:
        sb.storage.from_("product-images").upload(
            path, optimized, {"content-type": "image/webp", "upsert": "true"}
        )
        url: str = sb.storage.from_("product-images").get_public_url(path)
        
        # FIX: Supabase sometimes appends a trailing '?' for public URLs. Let's clean it.
        url = url.rstrip("?")
        
        logger.info("Image uploaded successfully: %s", path)
        return url
        
    except Exception as e:
        logger.error("Supabase upload failed for path %s: %s", path, e)
        raise RuntimeError("Failed to upload image to cloud storage.")