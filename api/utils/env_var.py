

from dotenv import load_dotenv
import os

load_dotenv() # TODO: Change .env file depending on the environment.


def get_env_var(var: str) -> str | None:
    return os.getenv(var)