from app.domains.users.schemas import AddressCreate, ProfileUpdate


def test_profile_email_is_validated_and_available_for_checkout():
    profile = ProfileUpdate(email="buyer@example.com")
    assert str(profile.email) == "buyer@example.com"


def test_address_requires_valid_confirmation_email():
    address = AddressCreate(
        line1="12 Main Street",
        city="Mumbai",
        state="MH",
        postal_code="400001",
        country="in",
        email="buyer@example.com",
    )
    assert str(address.email) == "buyer@example.com"


def test_address_rejects_invalid_email():
    try:
        AddressCreate(
            line1="12 Main Street",
            city="Mumbai",
            state="MH",
            postal_code="400001",
            country="IN",
            email="not-an-email",
        )
    except ValueError:
        return
    raise AssertionError("invalid checkout email must be rejected")
