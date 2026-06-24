from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken

from utils import get_env_var


def _get_key() -> bytes:
    key = get_env_var("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY environment variable is not set")
    return key.encode()


def encrypt(plain: any) -> str:
    return Fernet(_get_key()).encrypt(str(plain).encode()).decode()


def decrypt(token: any) -> str:
    return Fernet(_get_key()).decrypt(str(token).encode()).decode()


def decrypt_or_plain(value: any) -> str:
    if value is None:
        return None
    try:
        return decrypt(value)
    except InvalidToken:
        return str(value)
