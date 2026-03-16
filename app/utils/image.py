import io
import logging

from PIL import Image

from app.supabase_client import get_admin_supabase

Image.MAX_IMAGE_PIXELS = 10_000_000
logger = logging.getLogger(__name__)


def upload_product_image(file_bytes: bytes, product_id: str) -> str:
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert("RGB")
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=80)
    optimized = buffer.getvalue()

    sb = get_admin_supabase()
    path = f"products/{product_id}.webp"
    sb.storage.from_("product-images").upload(
        path, optimized, {"content-type": "image/webp", "upsert": "true"}
    )
    url: str = sb.storage.from_("product-images").get_public_url(path)
    logger.info("Image uploaded: %s", path)
    return url