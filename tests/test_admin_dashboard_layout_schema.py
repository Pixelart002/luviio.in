from __future__ import annotations
# ruff: noqa: I001 - maintain the local test import grouping.

import pytest

from pydantic import ValidationError

from app.domains.admin.schemas import AdminDashboardLayout


WIDGETS = [
    "metrics",
    "revenue",
    "status",
    "orders",
    "inventory",
    "payments",
    "audit",
    "notifications",
    "stripe",
]


def valid_layout() -> dict[str, object]:
    return {
        "order": WIDGETS.copy(),
        "hidden": ["status"],
        "sizes": {
            "metrics": "full",
            "revenue": "full",
            "status": "half",
            "orders": "full",
            "inventory": "half",
            "payments": "full",
            "audit": "half",
            "notifications": "half",
            "stripe": "half",
        },
    }


def test_dashboard_layout_accepts_all_supported_widgets() -> None:
    layout = AdminDashboardLayout.model_validate(valid_layout())
    assert layout.order == WIDGETS
    assert layout.hidden == ["status"]
    assert layout.sizes["revenue"] == "full"


def test_dashboard_layout_rejects_duplicate_or_missing_order_entries() -> None:
    payload = valid_layout()
    payload["order"] = [*WIDGETS[:-1], "metrics"]

    with pytest.raises(ValidationError):
        AdminDashboardLayout.model_validate(payload)


def test_dashboard_layout_rejects_duplicate_hidden_widgets() -> None:
    payload = valid_layout()
    payload["hidden"] = ["status", "status"]

    with pytest.raises(ValidationError):
        AdminDashboardLayout.model_validate(payload)


def test_dashboard_layout_rejects_incomplete_size_map() -> None:
    payload = valid_layout()
    payload["sizes"] = {"metrics": "full"}

    with pytest.raises(ValidationError):
        AdminDashboardLayout.model_validate(payload)


def test_dashboard_layout_rejects_unknown_fields_and_sizes() -> None:
    payload = valid_layout()
    payload["unrecognized"] = True
    payload["sizes"]["metrics"] = "thirds"

    with pytest.raises(ValidationError):
        AdminDashboardLayout.model_validate(payload)
