from cryptography.fernet import Fernet
from utils import get_env_var

def _get_key() -> bytes:
    key = get_env_var("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY environment variable is not set")
    return key.encode()

def encrypt(plain: any) -> str:
    if plain is None:
        return None
    return Fernet(_get_key()).encrypt(str(plain).encode()).decode()

def decrypt(token: any) -> str:
    if token is None:
        return None
    return Fernet(_get_key()).decrypt(str(token).encode()).decode()
