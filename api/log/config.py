import re
import os
from datetime import datetime
from string import Template

import aiofiles

from utils import get_env_var
from utils import project_root


class RelationalLogger:
    def __init__(self, log_format: str | None = None):
        self._log_file_dir_ = get_env_var("LOG_PATH") if get_env_var("LOG_PATH") is not None else f"{project_root}/log/"
        self._log_file_format_ = f".{re.sub(r'[^a-zA-Z0-9]', '', log_format)}.log" if log_format else ".log"
        self.partition_by = datetime.now().strftime("%Y_%m_%d")
        self._log_path_ = f"{self._log_file_dir_}/{self.partition_by}{self._log_file_format_}"
        self._env_ = get_env_var("ENV") if get_env_var("ENV") is not None else "dev"

        self.sep = "|"
        self.row_sep = "\n"
        self.headers = ["MODE", "CREATED_AT", "MODULE", "MESSAGE", "OBS"]
        self.time_format = "%Y-%m-%d %H:%M:%S"
        self.format = Template(f"""$mode {self.sep} $timestamp {self.sep} $module {self.sep} $primary_message {self.sep} $obs {self.row_sep}""")

    async def init(self):
        if not os.path.exists(self._log_file_dir_):
            os.makedirs(self._log_file_dir_)
        if not os.path.exists(self._log_path_):
            async with aiofiles.open(self._log_path_, "w") as f:
                await f.write(f" {self.sep} ".join(self.headers + [self.row_sep]))
        return self

    async def _write_log_(self, log_message: str):
        async with aiofiles.open(self._log_path_, "a") as f:
            await f.write(log_message)

    async def error(self, module:str, error_type:str, exception: str | None = None):
        await self._write_log_(
            self.format.substitute(
                mode="ERROR",
                primary_message=error_type,
                timestamp=datetime.now().strftime(self.time_format),
                obs=str(exception).replace("\n", "") if exception else None,
                module=module
            )
        )

    async def info(self, module:str, info_type:str, message:str):
        await self._write_log_(
            self.format.substitute(
                mode="INFO", primary_message=info_type,
                timestamp=datetime.now().strftime(self.time_format),
                obs=message,
                module=module
            )
        )

logger = RelationalLogger()