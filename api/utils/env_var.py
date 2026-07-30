

from dotenv import load_dotenv
import os

# TODO: Change .env file depending on the environment.
load_dotenv()


def get_env_var(var: str) -> str | None:
    return os.getenv(var)
