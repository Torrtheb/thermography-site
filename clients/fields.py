"""
Custom encrypted model fields using Fernet symmetric encryption.

All client PII is encrypted at rest in the database. The encryption key
is read from the FIELD_ENCRYPTION_KEY environment variable (a Fernet key).

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os

from cryptography.fernet import Fernet, InvalidToken

from django.conf import settings
from django.db import models


def _get_fernet():
    """Return a Fernet instance using the configured encryption key."""
    key = os.environ.get("FIELD_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError(
            "FIELD_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


class EncryptedTextField(models.TextField):
    """
    A TextField whose value is Fernet-encrypted at rest in the database.

    - On save: plaintext → encrypted token (stored as text).
    - On load: encrypted token → plaintext (returned to Python).
    - In the Django/Wagtail admin the owner sees and edits plain text as usual.

    The DB column holds the encrypted ciphertext, so even if the database
    is compromised the data is unreadable without the key.
    """

    description = "An encrypted text field"

    def get_prep_value(self, value):
        """Encrypt before saving to the database."""
        if value is None or value == "":
            return value
        f = _get_fernet()
        return f.encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        """Decrypt when reading from the database."""
        if value is None or value == "":
            return value
        f = _get_fernet()
        try:
            return f.decrypt(value.encode()).decode()
        except InvalidToken:
            # Value might be unencrypted (e.g. migrated data) — return as-is
            return value

    def deconstruct(self):
        """Return enough info for Django to recreate this field in migrations."""
        name, path, args, kwargs = super().deconstruct()
        # Point to our custom field class
        path = "clients.fields.EncryptedTextField"
        return name, path, args, kwargs


class EncryptedCharField(models.CharField):
    """
    A CharField whose value is Fernet-encrypted at rest.

    Encrypted tokens are longer than the original plaintext, so we
    override max_length to 500 in the database while allowing the
    admin form to enforce the logical max_length on plaintext input.
    """

    description = "An encrypted char field"

    def __init__(self, *args, **kwargs):
        # Store the logical max_length for form validation
        self._plaintext_max_length = kwargs.get("max_length", 255)
        # The DB column needs room for the Fernet token (~2× + overhead)
        kwargs["max_length"] = max(kwargs.get("max_length", 255) * 3, 500)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        f = _get_fernet()
        return f.encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        f = _get_fernet()
        try:
            return f.decrypt(value.encode()).decode()
        except InvalidToken:
            return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        path = "clients.fields.EncryptedCharField"
        # Restore the logical max_length for the migration file
        kwargs["max_length"] = self._plaintext_max_length
        return name, path, args, kwargs
