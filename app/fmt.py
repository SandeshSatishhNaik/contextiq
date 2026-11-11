"""Human-friendly formatting shared by every answer."""
from __future__ import annotations

SYMBOL = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$"}


def money(amount: float | None, currency: str = "USD", dp: int = 2) -> str:
    if amount is None:
        return "an unknown amount"
    sign = "-" if amount < 0 else ""
    sym = SYMBOL.get(currency)
    body = f"{abs(amount):,.{dp}f}"
    return f"{sign}{sym}{body}" if sym else f"{sign}{currency} {body}"


def days(n: float) -> str:
    n = round(n)
    if n <= 0:
        return "today"
    return "1 day" if n == 1 else f"{n} days"


def nice(s: str) -> str:
    return s.replace("_", " ")
