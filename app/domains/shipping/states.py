from enum import StrEnum


class ShipmentStatus(StrEnum):
    CREATED = "created"
    SERVICEABLE = "serviceable"
    ORDER_CREATED = "order_created"
    AWB_ASSIGNED = "awb_assigned"
    PICKUP_SCHEDULED = "pickup_scheduled"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RTO = "rto"
    FAILED = "failed"


ALLOWED_TRANSITIONS = {
    ShipmentStatus.CREATED: {ShipmentStatus.SERVICEABLE, ShipmentStatus.FAILED, ShipmentStatus.CANCELLED},
    ShipmentStatus.SERVICEABLE: {ShipmentStatus.ORDER_CREATED, ShipmentStatus.FAILED, ShipmentStatus.CANCELLED},
    ShipmentStatus.ORDER_CREATED: {ShipmentStatus.AWB_ASSIGNED, ShipmentStatus.FAILED, ShipmentStatus.CANCELLED},
    ShipmentStatus.AWB_ASSIGNED: {ShipmentStatus.PICKUP_SCHEDULED, ShipmentStatus.PICKED_UP, ShipmentStatus.CANCELLED},
    ShipmentStatus.PICKUP_SCHEDULED: {ShipmentStatus.PICKED_UP, ShipmentStatus.FAILED, ShipmentStatus.CANCELLED},
    ShipmentStatus.PICKED_UP: {ShipmentStatus.IN_TRANSIT, ShipmentStatus.RTO, ShipmentStatus.FAILED},
    ShipmentStatus.IN_TRANSIT: {ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.RTO, ShipmentStatus.FAILED},
    ShipmentStatus.OUT_FOR_DELIVERY: {ShipmentStatus.DELIVERED, ShipmentStatus.RTO, ShipmentStatus.FAILED},
    ShipmentStatus.DELIVERED: set(),
    ShipmentStatus.CANCELLED: set(),
    ShipmentStatus.RTO: set(),
    ShipmentStatus.FAILED: set(),
}


def can_transition(current: ShipmentStatus, target: ShipmentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
