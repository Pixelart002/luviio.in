from app.supabase_client import get_admin_supabase

def upload_product_image(file_bytes: bytes, product_slug: str) -> str:
    sb = get_admin_supabase()
    path = f"products/{product_slug}.webp"
    sb.storage.from_("product-images").upload(
        path,
        file_bytes,
        {"content-type": "image/webp", "upsert": "true"}
    )
    return sb.storage.from_("product-images").get_public_url(path)