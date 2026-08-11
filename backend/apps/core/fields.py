"""
Encrypted model fields — transparent AES-256-GCM at-rest encryption.

- EncryptedTextField: string values (tokens, keys)
- EncryptedJSONField: JSON values (sources, destinations, credentials)

Both store ciphertext in a TEXT column and decrypt on read. DRF serializers
MUST declare EncryptedJSONField columns explicitly as serializers.JSONField()
(see each app's serializers.py) because DRF maps model field types to
serializer field types by class — a TextField subclass maps to CharField.

Storage format: `$e$` + base64(nonce + ciphertext). Legacy plaintext and
legacy marker-less original ciphertext are detected and handled on read.
"""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.services.encryption import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """TextField that stores AES-256-GCM-encrypted strings."""

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt(value)

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        return decrypt(value)


class EncryptedJSONField(models.TextField):
    """JSON field whose serialized payload is AES-256-GCM-encrypted at rest."""

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        if isinstance(value, (dict, list)):
            value = json.dumps(value, cls=DjangoJSONEncoder)
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        decrypted = decrypt(value)
        try:
            return json.loads(decrypted)
        except (json.JSONDecodeError, TypeError):
            # Legacy plaintext JSON or malformed — return raw string.
            return decrypted

    def to_python(self, value):
        if isinstance(value, (dict, list)):
            return value
        if value is None or value == "":
            return value
        decrypted = decrypt(value)
        try:
            return json.loads(decrypted)
        except (json.JSONDecodeError, TypeError):
            return decrypted
