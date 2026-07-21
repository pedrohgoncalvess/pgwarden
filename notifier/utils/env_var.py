import os

from dotenv import load_dotenv


load_dotenv()


def get_env_var(var: str, default: str | None = None) -> str:
    value = os.getenv(var, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {var}")
    return value
