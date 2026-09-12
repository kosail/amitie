"""Password hashing (stdlib only — no new dependency for a hackathon-scale
demo auth system). PBKDF2-HMAC-SHA256 with a random per-user salt; nothing
here ever stores or logs a plaintext password (INV-040).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_ALGORITHM = "sha256"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (password_hash, salt) as hex strings. Generates a new salt if none is given."""
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        _ALGORITHM, password.encode("utf-8"), resolved_salt.encode("utf-8"), _ITERATIONS
    )
    return digest.hex(), resolved_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)
