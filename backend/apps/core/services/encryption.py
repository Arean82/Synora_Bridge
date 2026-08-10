"""
Encryption service â€” AES-256-GCM at-rest protection for sensitive fields.

Faithful port of the original bridge_app/services/encryption.py, hardened:
- marker-prefixed ciphertext (`$e$`) so encrypted values are unambiguous
- legacy plaintext / legacy original-format values are detected and returned as-is
- production refuses to boot with an unset ENCRYPTION_KEY; dev derives a key
  from SECRET_KEY so local data is still encrypted at rest
"""
import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

# Marker distinguishing encrypted values from plaintext/legacy values.
CIPHER_MARKER = "$e$"

# AES-GCM combined payload = 12-byte nonce + 16-byte tag + ciphertext.
MIN_COMBINED_LENGTH = 28


def get_encryption_key() -> bytes:
    """Return the 32-byte AES-256 key, derived or explicit."""
    explicit = getattr(settings, "ENCRYPTION_KEY", "") or ""
    if explicit:
        try:
            return base64.b64decode(explicit.encode("utf-8"))
        except Exception:
            raise RuntimeError("ENCRYPTION_KEY is not valid base64.")

    if settings.DEBUG:
        # Local-dev convenience: still encrypted at rest, but deterministic.
        return hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()

    raise RuntimeError(
        "ENCRYPTION_KEY must be set in production (see backend/.env.example)."
    )


def encrypt(plain_text: str) -> str:
    """Encrypt a string, returning marker-prefixed base64 ciphertext."""
    if not plain_text:
        return plain_text
    key = get_encryption_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    cipher_text = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    combined = nonce + cipher_text
    return CIPHER_MARKER + base64.b64encode(combined).decode("utf-8")


def _try_legacy_decrypt(value: str) -> str | None:
    """Best-effort decrypt of legacy (marker-less) original ciphertext."""
    try:
        combined = base64.b64decode(value.encode("utf-8"))
    except Exception:
        return None
    if len(combined) < MIN_COMBINED_LENGTH:
        return None
    key = get_encryption_key()
    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(combined[:12], combined[12:], None).decode("utf-8")
    except (InvalidTag, ValueError, TypeError):
        return None


def decrypt(cipher_b64: str) -> str:
    """Decrypt a value. Returns plaintext untouched (legacy or unencrypted)."""
    if not cipher_b64:
        return cipher_b64
    if cipher_b64.startswith(CIPHER_MARKER):
        key = get_encryption_key()
        try:
            combined = base64.b64decode(cipher_b64[len(CIPHER_MARKER):].encode("utf-8"))
            if len(combined) < MIN_COMBINED_LENGTH:
                return cipher_b64
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(combined[:12], combined[12:], None).decode("utf-8")
        except (InvalidTag, ValueError, TypeError):
            return cipher_b64
    # Marker-less: try legacy original format, else treat as plaintext.
    legacy = _try_legacy_decrypt(cipher_b64)
    return legacy if legacy is not None else cipher_b64
