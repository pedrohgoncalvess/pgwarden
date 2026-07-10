import os

from dotenv import load_dotenv


load_dotenv()


def get_env_var(var: str) -> str:
    value = os.getenv(var)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {var}")
    return value
