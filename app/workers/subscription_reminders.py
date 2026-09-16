"""Single-instance worker for subscription expiry reminders.

Run this as a dedicated Koyeb Worker service with one instance. The API service
must not run this loop because the API currently uses multiple Uvicorn workers.
"""
from __future__ import annotations

import asyncio
import logging

from app.domains.subscriptions.service import SubscriptionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_once() -> None:
    service = SubscriptionService()
    generated = await service.generate_due_reminders()
    dispatched = await service.dispatch_pending_reminders()
    logger.info("[SUB REMINDER] generated=%s dispatched=%s", generated, dispatched)


async def main() -> None:
    while True:
        try:
            await run_once()
        except Exception:
            logger.exception("[SUB REMINDER] worker cycle failed")
        await asyncio.sleep(24 * 60 * 60)


if __name__ == "__main__":
    asyncio.run(main())
