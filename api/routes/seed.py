from fastapi import APIRouter, HTTPException
from api.services.supabase_client import get_supabase_client

router = APIRouter()

@router.post("/seed")
async def seed_database(secret: str):
    # Simple secret check (you can use an env var)
    if secret != os.getenv("SEED_SECRET"):
        raise HTTPException(403, "Forbidden")
    client = get_supabase_client(use_service_role=True)

    # Example: insert navigation items
    nav_data = [
        {"label": "The Studio", "url": "/studio", "active": True, "page": "home"},
        {"label": "Materials", "url": "/materials", "active": False, "page": "home"},
    ]
    client.table("navigation").insert(nav_data).execute()

    # Insert footer sections and links
    # ... etc.

    return {"message": "Database seeded successfully"}