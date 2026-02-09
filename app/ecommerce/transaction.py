import asyncio
from app.db.client import supabase_client

async def execute_transaction(queries):
    """
    Executes multiple queries atomically
    """
    async with supabase_client.transaction() as trx:
        try:
            results = []
            for query in queries:
                result = await trx.execute(query)
                results.append(result)
            await trx.commit()
            return results
        except Exception as e:
            await trx.rollback()
            raise e