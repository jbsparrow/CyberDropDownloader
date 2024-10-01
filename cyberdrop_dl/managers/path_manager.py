import os
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.utils.dataclasses.url_objects import MediaItem

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

if os.getenv("PYCHARM_HOSTED") is not None or 'TERM_PROGRAM' in os.environ.keys() and os.environ[
    'TERM_PROGRAM'] == 'vscode':
    """This is for testing purposes only"""
    if os.getcwd().endswith("cyberdrop_dl"):
        APP_STORAGE = Path("../AppData")
        DOWNLOAD_STORAGE = Path("../Downloads")
    else:
        APP_STORAGE = Path("./AppData")
        DOWNLOAD_STORAGE = Path("./Downloads")
else:
    APP_STORAGE = Path("./AppData")
    DOWNLOAD_STORAGE = Path("./Downloads")


class PathManager:
    def __init__(self, manager: 'Manager'):
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
        self._completed_downloads = set()
        self._completed_downloads_set = set()
        self._prev_downloads = set()
        self._prev_downloads_set = set()

    def pre_startup(self) -> None:
        if self.manager.args_manager.appdata_dir:
            global APP_STORAGE
            APP_STORAGE = Path(self.manager.args_manager.appdata_dir) / "AppData"

        self.cache_dir = APP_STORAGE / "Cache"
        self.config_dir = APP_STORAGE / "Configs"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.cache_db = self.cache_dir / "request_cache.db"
        self.cache_db.touch(exist_ok=True)

    def startup(self) -> None:
        """Startup process for the Directory Manager"""
        self.download_dir = self.manager.config_manager.settings_data['Files'][
            'download_folder'] if not self.manager.args_manager.download_dir else self.manager.args_manager.download_dir
        self.sorted_dir = self.manager.config_manager.settings_data['Sorting'][
            'sort_folder'] if not self.manager.args_manager.sort_folder else self.manager.args_manager.sort_folder

        self.scan_dir = self.manager.config_manager.settings_data['Sorting'][
            'scan_folder'] if not self.manager.args_manager.scan_folder else self.manager.args_manager.scan_folder
        self.log_dir = self.manager.config_manager.settings_data['Logs'][
            'log_folder'] if not self.manager.args_manager.log_dir else self.manager.args_manager.log_dir
        self.input_file = self.manager.config_manager.settings_data['Files'][
            'input_file'] if not self.manager.args_manager.input_file else self.manager.args_manager.input_file
        self.history_db = self.cache_dir / "cyberdrop.db"

        self.main_log = self.log_dir / (self.manager.config_manager.settings_data['Logs']['main_log_filename']
                                        if not self.manager.args_manager.main_log_filename else self.manager.args_manager.main_log_filename)
        self.last_post_log = self.log_dir / (
            self.manager.config_manager.settings_data['Logs']['last_forum_post_filename']
            if not self.manager.args_manager.last_forum_post_filename else self.manager.args_manager.last_forum_post_filename)
        self.unsupported_urls_log = self.log_dir / (
            self.manager.config_manager.settings_data['Logs']['unsupported_urls_filename']
            if not self.manager.args_manager.unsupported_urls_filename else self.manager.args_manager.unsupported_urls_filename)
        self.download_error_log = self.log_dir / (
            self.manager.config_manager.settings_data['Logs']['download_error_urls_filename']
            if not self.manager.args_manager.download_error_urls_filename else self.manager.args_manager.download_error_urls_filename)
        self.scrape_error_log = self.log_dir / (
            self.manager.config_manager.settings_data['Logs']['scrape_error_urls_filename']
            if not self.manager.args_manager.scrape_error_urls_filename else self.manager.args_manager.scrape_error_urls_filename)

        self.log_dir.mkdir(parents=True, exist_ok=True)
        if not self.input_file.is_file():
            self.input_file.touch(exist_ok=True)
        self.history_db.touch(exist_ok=True)

    def add_completed(self, media_item: MediaItem):
        self._completed_downloads.add(media_item)
        self._completed_downloads_set.add(media_item.complete_file.absolute())

    def add_prev(self, media_item: MediaItem):
        self._prev_downloads.add(media_item)
        self._prev_downloads_set.add(media_item.complete_file.absolute())

    @property
    def completed_downloads(self):
        return self._completed_downloads

    @property
    def prev_downloads(self):
        return self._prev_downloads

    @property
    def completed_downloads_paths(self):
        return self._completed_downloads_set

    @property
    def prev_downloads_paths(self):
        return self._prev_downloads_set
