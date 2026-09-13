"""Payment domain model.

Fixture file for the MAAT offline pipeline (Problem_doc.md section 7).
"""


class Payment:
    """A single payment."""

    def __init__(self, amount: float, currency: str = "USD") -> None:
        self.amount = amount
        self.currency = currency
