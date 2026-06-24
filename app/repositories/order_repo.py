async def cancel_order_and_restore_stock(
    self,
    order_id: str,
    user_id: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """
    Atomic cancellation + stock restoration.

    Uses PostgreSQL RPC:
        cancel_order_and_release_stock()

    Benefits:
    - No manual stock loops
    - No increment_stock dependency
    - No partial restores
    - ACID compliant
    - Race-condition safe
    """

    logger.info(
        f"[REPO:ORDERS] Attempting atomic cancel for order {order_id}. User filter: {user_id}"
    )

    try:
        # Ownership validation for customer routes
        if user_id:
            existing_order = await self.get_order_by_id(order_id, user_id)
            if not existing_order:
                logger.warning(
                    f"[REPO:ORDERS] Order {order_id} not found or access denied."
                )
                return None

        rpc_res = await self.admin_sb.rpc(
            "cancel_order_and_release_stock",
            {
                "p_order_id": order_id
            }
        ).execute()

        result = getattr(rpc_res, "data", None)

        logger.info(
            f"[REPO:ORDERS] cancel_order_and_release_stock result: {result}"
        )

        if result == "ALREADY_CANCELLED":
            logger.info(
                f"[REPO:ORDERS] Order {order_id} already cancelled."
            )

        elif result != "SUCCESS":
            logger.error(
                f"[REPO:ORDERS] Unexpected RPC response for {order_id}: {result}"
            )
            return None

        updated_order = await self.get_order_by_id(order_id)

        logger.info(
            f"[REPO:ORDERS] Atomic cancellation completed successfully for {order_id}"
        )

        return updated_order

    except Exception as e:
        logger.error(
            f"[REPO:ORDERS] Atomic cancellation failed for {order_id}: {e}",
            exc_info=True
        )
        return None