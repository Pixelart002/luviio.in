from decimal import Decimal


def split_gst(tax_amount: Decimal, tax_type: str) -> tuple[Decimal, Decimal, Decimal]:
    if tax_type == "CGST+SGST":
        cgst = (tax_amount / 2).quantize(Decimal("0.01"))
        sgst = tax_amount - cgst
        return cgst, sgst, Decimal("0")
    if tax_type == "IGST":
        return Decimal("0"), Decimal("0"), tax_amount
    return Decimal("0"), Decimal("0"), Decimal("0")


def test_intra_state_gst_split_preserves_total():
    tax = Decimal("140.34")
    cgst, sgst, igst = split_gst(tax, "CGST+SGST")
    assert cgst == Decimal("70.17")
    assert sgst == Decimal("70.17")
    assert igst == Decimal("0")
    assert cgst + sgst + igst == tax


def test_inter_state_gst_split_uses_igst():
    tax = Decimal("140.34")
    cgst, sgst, igst = split_gst(tax, "IGST")
    assert cgst == Decimal("0")
    assert sgst == Decimal("0")
    assert igst == tax
