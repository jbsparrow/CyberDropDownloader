from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import platformdirs

from cyberdrop_dl.utils import constants, yaml
from cyberdrop_dl.utils.transfer.transfer_hash_db import transfer_from_old_hash_table
from cyberdrop_dl.utils.transfer.transfer_v4_config import transfer_v4_config
from cyberdrop_dl.utils.transfer.transfer_v4_db import transfer_v4_db

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class TransitionManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

    def transfer_v5_to_new_hashtable(self):
        """
        transfers from old v5 hash table to new v5 hash table, that supports multiple hash types per file
        """
        db_path = constants.APP_STORAGE / "Cache" / "cyberdrop.db"
        if db_path.exists():
            transfer_from_old_hash_table(db_path)

    def transfer_v4_to_v5(self):
        """
        Makes some changes for transfer from v4 to v5

        """
        OLD_APP_STORAGE = Path(platformdirs.user_config_dir("Cyberdrop-DL"))
        OLD_DOWNLOAD_STORAGE = Path(platformdirs.user_downloads_path()) / "Cyberdrop-DL Downloads"

        if constants.APP_STORAGE.exists():
            cache_file = constants.APP_STORAGE / "Cache" / "cache.yaml"
            if cache_file.is_file() and self.check_cache_for_moved(cache_file):
                return

        OLD_FILES = Path("./Old Files")
        OLD_FILES.mkdir(parents=True, exist_ok=True)

        if OLD_APP_STORAGE.exists():
            if constants.APP_STORAGE.exists():
                if constants.APP_STORAGE.with_name("AppData_OLD").exists():
                    constants.APP_STORAGE.rename(constants.APP_STORAGE.with_name("AppData_OLD2"))
                constants.APP_STORAGE.rename(constants.APP_STORAGE.with_name("AppData_OLD"))
            shutil.copytree(OLD_APP_STORAGE, constants.APP_STORAGE, dirs_exist_ok=True)
            shutil.rmtree(OLD_APP_STORAGE)

        if OLD_DOWNLOAD_STORAGE.exists():
            shutil.copytree(OLD_DOWNLOAD_STORAGE, constants.DOWNLOAD_STORAGE, dirs_exist_ok=True)
            shutil.rmtree(OLD_DOWNLOAD_STORAGE)

        if Path("./download_history.sqlite").is_file():
            transfer_v4_db(Path("./download_history.sqlite"), constants.APP_STORAGE / "Cache" / "cyberdrop.db")
            Path("./download_history.sqlite").rename(OLD_FILES / "download_history1.sqlite")

        if (constants.APP_STORAGE / "download_history.sqlite").is_file():
            transfer_v4_db(
                constants.APP_STORAGE / "download_history.sqlite",
                constants.APP_STORAGE / "Cache" / "cyberdrop.db",
            )
            (constants.APP_STORAGE / "download_history.sqlite").rename(OLD_FILES / "download_history2.sqlite")

        if Path("./config.yaml").is_file():
            try:
                transfer_v4_config(self.manager, "Imported V4", Path("./config.yaml"))
                self.update_default_config(constants.APP_STORAGE / "Cache" / "cache.yaml", "Imported V4")
            except OSError:
                pass
            Path("./config.yaml").rename(OLD_FILES / "config.yaml")

        if Path("./Errored_Download_URLs.csv").is_file():
            Path("./Errored_Download_URLs.csv").rename(OLD_FILES / "Errored_Download_URLs.csv")
        if Path("./Errored_Scrape_URLs.csv").is_file():
            Path("./Errored_Scrape_URLs.csv").rename(OLD_FILES / "Errored_Scrape_URLs.csv")
        if Path("./Unsupported_URLs.csv").is_file():
            Path("./Unsupported_URLs.csv").rename(OLD_FILES / "Unsupported_URLs.csv")

        self.set_first_startup_completed(constants.APP_STORAGE / "Cache" / "cache.yaml")

    @staticmethod
    def check_cache_for_moved(cache_file: Path) -> bool:
        """Checks the cache for moved files."""
        cache = yaml.load(cache_file, create=True)
        if not cache:
            cache = {"first_startup_completed": False}
            yaml.save(cache_file, cache)
        return bool(cache.get("first_startup_completed", False))

    @staticmethod
    def set_first_startup_completed(cache_file: Path) -> None:
        """Updates the cache to reflect the new location."""
        cache = yaml.load(cache_file, create=True)
        cache["first_startup_completed"] = True
        yaml.save(cache_file, cache)

    @staticmethod
    def update_default_config(cache_file: Path, config_name: str) -> None:
        """Updates the default config in the cache."""
        cache = yaml.load(cache_file, create=True)
        if not cache:
            cache = {"first_startup_completed": False}
        cache["default_config"] = config_name
        yaml.save(cache_file, cache)
