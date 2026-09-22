"""Phone-number normalization helpers."""
from __future__ import annotations

import re


class InvalidIndianMobile(ValueError):
    """Raised when a value cannot be normalized to an Indian mobile number."""


def normalize_indian_mobile(value: object) -> str:
    """Return a canonical 10-digit Indian mobile number.

    Accepted input forms include 10 digits, +91XXXXXXXXXX, 91XXXXXXXXXX,
    0091XXXXXXXXXX, and the common 0XXXXXXXXXX domestic form.
    """
    raw = str(value or "").strip()
    if not raw:
        raise InvalidIndianMobile("Phone number is required.")

    digits = re.sub(r"\D", "", raw)

    if digits.startswith("0091") and len(digits) == 14:
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if not re.fullmatch(r"[6-9][0-9]{9}", digits) or len(set(digits)) == 1:
        raise InvalidIndianMobile(
            "Phone number must be a valid 10-digit Indian mobile number."
        )

    return digits
