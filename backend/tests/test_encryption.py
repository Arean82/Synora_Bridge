"""Encryption service + encrypted field tests."""
import pytest

from apps.core.fields import EncryptedJSONField, EncryptedTextField
from apps.core.services.encryption import CIPHER_MARKER, decrypt, encrypt


class TestEncryptionService:
    def test_roundtrip(self):
        plain = "sensitive-token-123"
        cipher = encrypt(plain)
        assert cipher != plain
        assert cipher.startswith(CIPHER_MARKER)
        assert decrypt(cipher) == plain

    def test_empty_values_pass_through(self):
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_plaintext_passthrough(self):
        # Legacy/unencrypted values are returned untouched.
        assert decrypt("legacy-plaintext") == "legacy-plaintext"

    def test_tampered_ciphertext_returns_raw(self):
        cipher = encrypt("hello")
        tampered = cipher[:-4] + "XXXX"
        assert decrypt(tampered) == tampered  # no crash, no garbage


class TestEncryptedFields:
    """Field-level round-trips through the DB-prep / DB-read hooks.

    Exercises get_prep_value (encrypt on write) and from_db_value (decrypt on
    read) directly, which is exactly what Django calls around a real column.
    """

    def test_text_field_roundtrip(self):
        field = EncryptedTextField()
        prepared = field.get_prep_value("tok-abc")
        assert prepared is not None and prepared != "tok-abc"
        assert str(prepared).startswith(CIPHER_MARKER)
        assert field.from_db_value(prepared, None, None) == "tok-abc"

    def test_text_field_none(self):
        field = EncryptedTextField()
        assert field.get_prep_value(None) is None
        assert field.from_db_value(None, None, None) is None

    def test_json_field_roundtrip(self):
        field = EncryptedJSONField(default=dict, blank=True)
        value = {"token": "x", "list": [1, 2], "nested": {"a": "b"}}
        prepared = field.get_prep_value(value)
        assert prepared != value
        assert field.from_db_value(prepared, None, None) == value

    def test_json_field_none(self):
        field = EncryptedJSONField(default=dict, blank=True)
        assert field.get_prep_value(None) is None
        assert field.from_db_value(None, None, None) is None
