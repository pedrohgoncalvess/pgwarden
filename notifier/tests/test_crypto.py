"""Tests for notifier.utils.crypto (Fernet encrypt/decrypt helpers)."""

import pytest
from cryptography.fernet import Fernet

from notifier.utils import crypto


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


def test_get_key_returns_encoded_bytes(encryption_key):
    assert crypto._get_key() == encryption_key.encode()


def test_get_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        crypto._get_key()


def test_encrypt_decrypt_roundtrip(encryption_key):
    plain = "super-secret-webhook-token"
    token = crypto.encrypt(plain)

    assert token != plain
    assert crypto.decrypt(token) == plain


def test_encrypt_coerces_non_str_to_str(encryption_key):
    token = crypto.encrypt(12345)
    assert crypto.decrypt(token) == "12345"


def test_decrypt_or_plain_returns_plain_when_valid(encryption_key):
    token = crypto.encrypt("payload")
    assert crypto.decrypt_or_plain(token) == "payload"


def test_decrypt_or_plain_returns_raw_value_when_key_wrong(encryption_key, monkeypatch):
    # Encrypt with the fixture key, then swap to a different key so decryption fails.
    token = crypto.encrypt("payload")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())

    result = crypto.decrypt_or_plain(token)

    assert result == token  # falls back to the raw (undecryptable) value


def test_decrypt_or_plain_returns_none_for_none_input(encryption_key):
    # Documents current behaviour: a None value short-circuits to None.
    assert crypto.decrypt_or_plain(None) is None
