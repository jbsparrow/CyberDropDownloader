from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from cyberdrop_dl import constants
from cyberdrop_dl.utils.utilities import purge_dir_tree

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.config._common import PathAliasModel
    from cyberdrop_dl.managers.manager import Manager


def pre_startup(self) -> None:
    _cache_folder = constants.APP_STORAGE / "Cache"
    _config_folder = constants.APP_STORAGE / "Configs"
    _cookies_dir = constants.APP_STORAGE / "Cookies"
    _cache_db = _cache_folder / "request_cache.db"
    _history_db = _cache_folder / "cyberdrop.db"
    _log_folder.mkdir(parents=True, exist_ok=True)

    for path in (_cache_folder, _config_folder, _cookies_dir, _log_folder):
        path.mkdir(parents=True, exist_ok=True)
    _cache_db.touch(exist_ok=True)


def startup(self, _manager: Manager, config_name: str) -> None:
    settings_data: PathAliasModel = _manager.config_manager.settings_data
    settings_data.resolve_paths(config_name)

    now = datetime.now()
    settings_data.logs.set_output_filenames(now)
    __delete_logs_and_folders(now)

    if not _input_file.is_file():
        _input_file.touch(exist_ok=True)
    _history_db.touch(exist_ok=True)

    _pages_folder = _main_log.parent / "cdl_responses"


def __delete_logs_and_folders(
    log_folder: Path, now: datetime | None = None, expire_after: timedelta | None = None
) -> None:
    if now and expire_after:
        for file in itertools.chain(log_folder.rglob("*.log"), log_folder.rglob("*.csv")):
            file_date = file.stat().st_ctime
            t_delta = now - datetime.fromtimestamp(file_date)
            if t_delta > expire_after:
                file.unlink(missing_ok=True)
    purge_dir_tree(log_folder)
