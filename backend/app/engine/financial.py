"""Financial calculation: order of operations is policy-critical.

Network discount is applied FIRST on the covered amount, co-pay SECOND on the
discounted amount (test case TC010 pins this ordering).

Input:  covered amount + category terms + network status.
Output: FinancialBreakdown with every intermediate figure, so the trace can
        show the math.
Errors: none raised; inputs are assumed validated upstream.
"""

from __future__ import annotations

from app.models.decision import FinancialBreakdown
from app.models.policy import OpdCategory


def compute_payable(
    claimed_amount: float,
    covered_amount: float,
    category: OpdCategory,
    is_network_hospital: bool,
) -> FinancialBreakdown:
    notes: list[str] = []

    discount_pct = category.network_discount_percent if is_network_hospital else 0.0
    discount_amt = round(covered_amount * discount_pct / 100, 2)
    after_discount = round(covered_amount - discount_amt, 2)
    if discount_pct:
        notes.append(
            f"Network discount ({discount_pct:g}%) applied first on "
            f"₹{covered_amount:g} = ₹{after_discount:g}."
        )

    copay_pct = category.copay_percent
    copay_amt = round(after_discount * copay_pct / 100, 2)
    payable = round(after_discount - copay_amt, 2)
    if copay_pct:
        notes.append(
            f"Co-pay ({copay_pct:g}%) applied on ₹{after_discount:g} = "
            f"₹{copay_amt:g} deducted."
        )
    notes.append(f"Final payable: ₹{payable:g}.")

    return FinancialBreakdown(
        claimed_amount=claimed_amount,
        covered_amount=covered_amount,
        network_discount_percent=discount_pct,
        network_discount_amount=discount_amt,
        amount_after_discount=after_discount,
        copay_percent=copay_pct,
        copay_amount=copay_amt,
        payable_amount=payable,
        notes=notes,
    )
