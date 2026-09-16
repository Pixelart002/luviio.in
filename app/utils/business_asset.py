"""Business profile asset uploads (logo/signature) to Supabase Storage."""
from __future__ import annotations

import io
import logging
import uuid
from urllib.parse import unquote, urlparse

from PIL import Image, UnidentifiedImageError

from app.core.supabase import get_admin_supabase

logger = logging.getLogger(__name__)
BUCKET = "business-assets"
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000
PUBLIC_PREFIX = "/storage/v1/object/public/business-assets/"


def _validate(data: bytes, filename: str) -> None:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Asset must be between 1 byte and 5 MB.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("Image dimensions are too large.")
            image.verify()
    except UnidentifiedImageError as exc:
        raise ValueError(f"Invalid image file: {filename}") from exc


def _encode(data: bytes, *, signature: bool) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        if signature:
            image = image.convert("RGBA")
            image.thumbnail((1600, 500), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
        else:
            if image.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", image.size, "white")
                if image.mode == "P":
                    image = image.convert("RGBA")
                if image.mode in ("RGBA", "LA"):
                    bg.paste(image, mask=image.getchannel("A"))
                else:
                    bg.paste(image)
                image = bg
            else:
                image = image.convert("RGB")
            image.thumbnail((1600, 800), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, format="WEBP", quality=88, method=6)
        return out.getvalue()


def upload_business_asset(data: bytes, filename: str, asset_type: str) -> str:
    if asset_type not in {"logo", "signature"}:
        raise ValueError("Unsupported business asset type.")
    _validate(data, filename)
    signature = asset_type == "signature"
    encoded = _encode(data, signature=signature)
    extension = "png" if signature else "webp"
    path = f"{asset_type}/{uuid.uuid4().hex}.{extension}"
    content_type = "image/png" if signature else "image/webp"
    sb = get_admin_supabase()
    try:
        sb.storage.from_(BUCKET).upload(
            path,
            encoded,
            {"content-type": content_type, "upsert": "false", "cache-control": "public, max-age=31536000, immutable"},
        )
        return sb.storage.from_(BUCKET).get_public_url(path).split("?")[0]
    except Exception as exc:
        logger.error("Business asset upload failed | type=%s", asset_type, exc_info=True)
        raise RuntimeError("Failed to upload business asset. Please try again.") from exc


def _asset_path_from_public_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or PUBLIC_PREFIX not in parsed.path:
        return None
    path = unquote(parsed.path.split(PUBLIC_PREFIX, 1)[1]).lstrip("/")
    if not path or path.startswith("/") or ".." in path.split("/"):
        return None
    asset_type = path.split("/", 1)[0]
    if asset_type not in {"logo", "signature"}:
        return None
    return path


def delete_business_asset(url: str | None) -> bool:
    """Delete a Luviio-managed business asset; ignore external/invalid URLs."""
    path = _asset_path_from_public_url(url)
    if not path:
        return False
    try:
        get_admin_supabase().storage.from_(BUCKET).remove([path])
        return True
    except Exception:
        logger.warning("Business asset cleanup failed | path=%s", path, exc_info=True)
        return False
