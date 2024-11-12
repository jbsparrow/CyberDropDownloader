from __future__ import annotations

from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.utils import constants

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem


if constants.DEBUG_VAR and Path.cwd().name == "cyberdrop_dl":
    """This is for testing purposes only"""
    constants.APP_STORAGE = Path("../AppData")
    constants.DOWNLOAD_STORAGE = Path("../Downloads")


class PathManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

        self.download_dir: Path = field(init=False)
        self.sorted_dir: Path = field(init=False)
        self.scan_dir: Path = field(init=False)

        self.log_dir: Path = field(init=False)

        self.cache_dir: Path = field(init=False)
        self.config_dir: Path = field(init=False)

        self.input_file: Path = field(init=False)
        self.history_db: Path = field(init=False)
        self.cache_db: Path = field(init=False)

        self.main_log: Path = field(init=False)
        self.last_post_log: Path = field(init=False)
        self.unsupported_urls_log: Path = field(init=False)
        self.download_error_log: Path = field(init=False)
        self.scrape_error_log: Path = field(init=False)
        self._completed_downloads: set[MediaItem] = set()
        self._completed_downloads_set = set()
        self._prev_downloads = set()
        self._prev_downloads_set = set()

    def pre_startup(self) -> None:
        if self.manager.args_manager.appdata_dir:
            constants.APP_STORAGE = Path(self.manager.args_manager.appdata_dir) / "AppData"

        self.cache_dir = constants.APP_STORAGE / "Cache"
        self.config_dir = constants.APP_STORAGE / "Configs"
        self.cookies_dir = constants.APP_STORAGE / "Cookies"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.cache_db = self.cache_dir / "request_cache.db"
        self.cache_db.touch(exist_ok=True)

    def startup(self) -> None:
        """Startup process for the Directory Manager."""
        self.download_dir = (
            self.manager.args_manager.download_dir
            or self.manager.config_manager.settings_data["Files"]["download_folder"]
        )

        self.sorted_dir = (
            self.manager.args_manager.sort_folder or self.manager.config_manager.settings_data["Sorting"]["sort_folder"]
        )

        self.scan_dir = (
            self.manager.args_manager.scan_folder or self.manager.config_manager.settings_data["Sorting"]["scan_folder"]
        )

        self.log_dir = (
            self.manager.args_manager.log_dir or self.manager.config_manager.settings_data["Logs"]["log_folder"]
        )
        self.input_file = (
            self.manager.args_manager.input_file or self.manager.config_manager.settings_data["Files"]["input_file"]
        )

        self.history_db = self.cache_dir / "cyberdrop.db"

        current_time_iso = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_settings_config = self.manager.config_manager.settings_data["Logs"]
        log_args_config = self.manager.args_manager
        log_options_map = {
            "main_log_filename": "main_log",
            "last_forum_post_filename": "last_post_log",
            "unsupported_urls_filename": "unsupported_urls_log",
            "download_error_urls_filename": "download_error_log",
            "scrape_error_urls_filename": "scrape_error_log",
        }

        for log_config_name, log_internal_name in log_options_map.items():
            file_name = Path(getattr(log_args_config, log_config_name, None) or log_settings_config[log_config_name])
            file_ext = ".log" if log_internal_name == "main_log" else ".csv"
            if log_settings_config["rotate_logs"]:
                file_name = f"{file_name.stem}__{current_time_iso}{file_name.suffix}"
            log_path = self.log_dir.joinpath(file_name).with_suffix(file_ext)
            setattr(self, log_internal_name, log_path)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self.input_file.is_file():
            self.input_file.touch(exist_ok=True)
        self.history_db.touch(exist_ok=True)

    def add_completed(self, media_item: MediaItem) -> None:
        self._completed_downloads.add(media_item)
        self._completed_downloads_set.add(media_item.complete_file.absolute())

    def add_prev(self, media_item: MediaItem) -> None:
        self._prev_downloads.add(media_item)
        self._prev_downloads_set.add(media_item.complete_file.absolute())

    @property
    def completed_downloads(self) -> set[MediaItem]:
        return self._completed_downloads

    @property
    def prev_downloads(self) -> set:
        return self._prev_downloads

    @property
    def completed_downloads_paths(self) -> set:
        return self._completed_downloads_set

    @property
    def prev_downloads_paths(self) -> set:
        return self._prev_downloads_set
