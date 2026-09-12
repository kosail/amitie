"""Server-side CLABE validation.

Mirrors the frontend's `src/features/transfers/clabe.ts` mod-10 checksum
(weights 3-7-1 repeating) exactly, so the client and server never disagree on
what counts as a valid CLABE. The client's validation is UX only — this is
the one that actually gates a transfer, per INV-015 (deterministic money
logic never trusts the caller).
"""

from __future__ import annotations

_WEIGHTS = (3, 7, 1)


def is_valid_clabe(raw: str) -> bool:
    """True iff `raw` is exactly 18 digits and passes the CLABE checksum."""
    if raw is None:
        return False
    digits = raw.strip()
    if len(digits) != 18 or not digits.isdigit():
        return False

    total = 0
    for index in range(17):
        total += (int(digits[index]) * _WEIGHTS[index % 3]) % 10
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(digits[17])
