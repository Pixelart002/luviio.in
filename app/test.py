# test_discount_fix.py
import asyncio
from app.repositories.order_repo import AsyncOrderRepository

async def test_discount():
    repo = AsyncOrderRepository()
    # Replace with a real order_id from your system
    order = await repo.get_order_by_id("cb08a189-c768-48f0-a248-25fe1154a827")
    
    if order and order.get("order_items"):
        for item in order["order_items"]:
            products = item.get("products", {})
            print(f"Product: {products.get('name')}")
            print(f"  - Price: {products.get('price')}")
            print(f"  - Compare Price (MRP): {products.get('compare_price')}")  # ← Should NOT be None
            
asyncio.run(test_discount())