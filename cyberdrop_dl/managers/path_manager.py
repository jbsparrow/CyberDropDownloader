from __future__ import annotations

import os
from dataclasses import Field, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl import env
from cyberdrop_dl.utils.utilities import purge_dir_tree

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


class PathManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager

        self.download_folder: Path = field(init=False)
        self.sorted_folder: Path = field(init=False)
        self.scan_folder: Path | None = field(init=False)

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
        self.pages_folder: Path = field(init=False)

        self._logs_model_names = [
            "main_log",
            "last_forum_post",
            "unsupported_urls",
            "download_error_urls",
            "scrape_error_urls",
        ]
        self._appdata: Path = field(init=False)

    @property
    def cwd(self) -> Path:
        if env.RUNNING_IN_IDE and Path.cwd().name == "cyberdrop_dl":
            # This is for testing purposes only"""
            return Path("..").resolve()
        return Path().resolve()

    @property
    def appdata(self) -> Path:
        if isinstance(self._appdata, Field):
            if self.manager.parsed_args.cli_only_args.appdata_folder:
                path = self.manager.parsed_args.cli_only_args.appdata_folder / "AppData"
                self._appdata = self.cwd / path
            else:
                self._appdata = self.cwd / "AppData"

        return self._appdata

    def pre_startup(self) -> None:
        self.cache_folder = self.appdata / "Cache"
        self.config_folder = self.appdata / "Configs"
        self.cookies_dir = self.appdata / "Cookies"
        self.cache_db = self.cache_folder / "request_cache.db"

        self.cache_folder.mkdir(parents=True, exist_ok=True)
        self.config_folder.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db.touch(exist_ok=True)

    def startup(self) -> None:
        """Startup process for the Directory Manager."""
        settings_data = self.manager.config_manager.settings_data
        current_config = self.manager.config_manager.loaded_config

        def replace(path: Path) -> Path:
            path_w_config = str(path).replace("{config}", current_config)
            if os.name == "nt":
                return self.cwd.joinpath(Path(path_w_config)).resolve()
            normalized_path_str = path_w_config.replace("\\", "/")
            return self.cwd.joinpath(Path(normalized_path_str)).resolve()

        self.download_folder = replace(settings_data.files.download_folder)
        self.sorted_folder = replace(settings_data.sorting.sort_folder)
        self.log_folder = replace(settings_data.logs.log_folder)
        self.input_file = replace(settings_data.files.input_file)
        self.history_db = self.cache_folder / "cyberdrop.db"
        self.scan_folder = settings_data.sorting.scan_folder
        if self.scan_folder:
            self.scan_folder = replace(self.scan_folder)

        self.log_folder.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        self._set_output_filenames(now)
        self._delete_logs_and_folders(now)
        self._create_output_folders()

        if not self.input_file.is_file():
            self.input_file.touch(exist_ok=True)
        self.history_db.touch(exist_ok=True)

    def _set_output_filenames(self, now: datetime) -> None:
        current_time_file_iso: str = now.strftime("%Y%m%d_%H%M%S")
        current_time_folder_iso: str = now.strftime("%Y_%m_%d")
        log_settings_config = self.manager.config_manager.settings_data.logs
        log_files: dict[str, Path] = log_settings_config.model_dump()

        for model_name, log_file in log_files.items():
            if model_name not in self._logs_model_names:
                continue
            if log_settings_config.rotate_logs:
                new_name = f"{log_file.stem}_{current_time_file_iso}{log_file.suffix}"
                log_file: Path = log_file.parent / current_time_folder_iso / new_name
            log_files[model_name] = log_file

        log_settings_config = log_settings_config.model_copy(update=log_files)

        for model_name in self._logs_model_names:
            internal_name = f"{model_name.replace('_log', '')}_log"
            setattr(self, internal_name, self.log_folder / getattr(log_settings_config, model_name))

        self.pages_folder = self.main_log.parent / "cdl_responses"

    def _delete_logs_and_folders(self, now: datetime):
        if self.manager.config_manager.settings_data.logs.logs_expire_after:
            for file in set(self.log_folder.rglob("*.log")) | set(self.log_folder.rglob("*.csv")):
                file_date = Path(file).stat().st_ctime
                t_delta = now - datetime.fromtimestamp(file_date)
                if t_delta > self.manager.config_manager.settings_data.logs.logs_expire_after:
                    file.unlink(missing_ok=True)
        purge_dir_tree(self.log_folder)

    def _create_output_folders(self):
        for model_name in self._logs_model_names:
            internal_name = f"{model_name.replace('_log', '')}_log"
            path: Path = getattr(self, internal_name)
            path.parent.mkdir(parents=True, exist_ok=True)

        if self.manager.config_manager.settings_data.files.save_pages_html:
            self.pages_folder.mkdir(parents=True, exist_ok=True)

    def add_completed(self, media_item: MediaItem) -> None:
        if media_item.is_segment:
            return
        self._completed_downloads.add(media_item)
        self._completed_downloads_paths.add(media_item.complete_file)

    def add_prev(self, media_item: MediaItem) -> None:
        self._prev_downloads.add(media_item)
        self._prev_downloads_paths.add(media_item.complete_file)

    @property
    def completed_downloads(self) -> set[MediaItem]:
        return self._completed_downloads

    @property
    def prev_downloads(self) -> set[MediaItem]:
        return self._prev_downloads
