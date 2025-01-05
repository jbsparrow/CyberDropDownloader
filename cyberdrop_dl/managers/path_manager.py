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
        self.cache_db: Path = field(init=False)

        self._completed_downloads: set[MediaItem] = set()
        self._completed_downloads_paths: set[Path] = set()
        self._prev_downloads: set[MediaItem] = set()
        self._prev_downloads_paths: set[Path] = set()

        self.main_log: Path = field(init=False)
        self.last_forum_post_log: Path = field(init=False)
        self.unsupported_urls_log: Path = field(init=False)
        self.download_error_urls_log: Path = field(init=False)
        self.scrape_error_urls_log: Path = field(init=False)

        self._logs_model_names = [
            "main_log",
            "last_forum_post",
            "unsupported_urls",
            "download_error_urls",
            "scrape_error_urls",
        ]

    def pre_startup(self) -> None:
        if self.manager.parsed_args.cli_only_args.appdata_folder:
            constants.APP_STORAGE = self.manager.parsed_args.cli_only_args.appdata_folder / "AppData"

        self.cache_folder = constants.APP_STORAGE / "Cache"
        self.config_folder = constants.APP_STORAGE / "Configs"
        self.cookies_dir = constants.APP_STORAGE / "Cookies"
        self.cache_db = self.cache_folder / "request_cache.db"

        self.cache_folder.mkdir(parents=True, exist_ok=True)
        self.config_folder.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db.touch(exist_ok=True)

    def replace_config_in_path(self, path: Path) -> Path | None:
        current_config = self.manager.config_manager.loaded_config
        if path is None:
            return
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
        self._create_output_folders()

        if not self.input_file.is_file():
            self.input_file.touch(exist_ok=True)
        self.history_db.touch(exist_ok=True)

    def _set_output_filenames(self) -> None:
        current_time_iso = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_settings_config = self.manager.config_manager.settings_data.logs
        log_files: dict[str, Path] = log_settings_config.model_dump()

        for model_name, log_file in log_files.items():
            if model_name not in self._logs_model_names:
                continue
            if log_settings_config.rotate_logs:
                log_file = log_file.parent / f"{log_file.stem}__{current_time_iso}{log_file.suffix}"
            log_files[model_name] = log_file

        log_settings_config = log_settings_config.model_copy(update=log_files)

        for model_name in self._logs_model_names:
            internal_name = f"{model_name.replace('_log','')}_log"
            setattr(self, internal_name, self.log_folder / getattr(log_settings_config, model_name))

    def _create_output_folders(self):
        for model_name in self._logs_model_names:
            internal_name = f"{model_name.replace('_log','')}_log"
            path: Path = getattr(self, internal_name)
            path.parent.mkdir(parents=True, exist_ok=True)

    def add_completed(self, media_item: MediaItem) -> None:
        self._completed_downloads.add(media_item)
        self._completed_downloads_paths.add(media_item.complete_file.resolve())

    def add_prev(self, media_item: MediaItem) -> None:
        self._prev_downloads.add(media_item)
        self._prev_downloads_paths.add(media_item.complete_file.resolve())

    @property
    def completed_downloads(self) -> set[MediaItem]:
        return self._completed_downloads

    @property
    def prev_downloads(self) -> set[MediaItem]:
        return self._prev_downloads
