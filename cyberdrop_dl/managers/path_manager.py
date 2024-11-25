from __future__ import annotations

from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.utils import constants

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


if constants.DEBUG_VAR and Path.cwd().name == "cyberdrop_dl":
    """This is for testing purposes only"""
    constants.APP_STORAGE = Path("../AppData")
    constants.DOWNLOAD_STORAGE = Path("../Downloads")


class PathManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

        self.download_folder: Path = field(init=False)
        self.sorted_folder: Path = field(init=False)
        self.scan_folder: Path = field(init=False)

        self.log_folder: Path = field(init=False)

        self.cache_folder: Path = field(init=False)
        self.config_folder: Path = field(init=False)

        self.input_file: Path = field(init=False)
        self.history_db: Path = field(init=False)

        self._completed_downloads: set[MediaItem] = set()
        self._completed_downloads_set = set()
        self._prev_downloads = set()
        self._prev_downloads_set = set()

    def pre_startup(self) -> None:
        if self.manager.parsed_args.cli_only_args.appdata_folder:
            constants.APP_STORAGE = self.manager.parsed_args.cli_only_args.appdata_folder / "AppData"

        self.cache_folder = constants.APP_STORAGE / "Cache"
        self.config_folder = constants.APP_STORAGE / "Configs"
        self.cookies_dir = constants.APP_STORAGE / "Cookies"

        self.cache_folder.mkdir(parents=True, exist_ok=True)
        self.config_folder.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)

    def replace_config_in_path(self, path: Path) -> Path:
        current_config = self.manager.config_manager.loaded_config
        return Path(str(path).replace("{config}", current_config))

    def startup(self) -> None:
        """Startup process for the Directory Manager."""
        settings_data = self.manager.config_manager.settings_data
        self.download_folder = self.replace_config_in_path(settings_data.files.download_folder)
        self.sorted_folder = self.replace_config_in_path(settings_data.sorting.sort_folder)
        self.scan_folder = self.replace_config_in_path(settings_data.sorting.scan_folder)
        self.log_folder = self.replace_config_in_path(settings_data.logs.log_folder)
        self.input_file = self.replace_config_in_path(settings_data.files.input_file)
        self.history_db = self.cache_folder / "cyberdrop.db"

        self._set_output_filenames()

        self.log_folder.mkdir(parents=True, exist_ok=True)
        if not self.input_file.is_file():
            self.input_file.touch(exist_ok=True)
        self.history_db.touch(exist_ok=True)

    def _set_output_filenames(self) -> None:
        current_time_iso = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_settings_config = self.manager.config_manager.settings_data.logs
        log_files = log_settings_config.model_dump()

        for name, log_file in log_files.items():
            if "filename" not in name:
                continue
            is_main_log = log_file == log_settings_config.main_log_filename
            file_ext = ".log" if is_main_log else ".csv"
            file_name = log_file
            path = Path(log_file)
            if log_settings_config.rotate_logs:
                file_name = f"{path.stem}__{current_time_iso}{path.suffix}"
            log_files[name] = Path(file_name).with_suffix(file_ext).name
        log_settings_config = log_settings_config.model_copy(update=log_files)
        self.main_log = self.log_folder / log_settings_config.main_log_filename
        self.last_forum_post_log = self.log_folder / log_settings_config.last_forum_post_filename
        self.unsupported_urls_log = self.log_folder / log_settings_config.unsupported_urls_filename
        self.download_error_log = self.log_folder / log_settings_config.download_error_urls_filename
        self.scrape_error_log = self.log_folder / log_settings_config.scrape_error_urls_filename

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
