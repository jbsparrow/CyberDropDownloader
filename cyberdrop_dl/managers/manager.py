from __future__ import annotations

import json
from dataclasses import Field, field
from time import perf_counter
from typing import TYPE_CHECKING

from cyberdrop_dl import __version__
from cyberdrop_dl.config_definitions import ConfigSettings, GlobalSettings
from cyberdrop_dl.managers.cache_manager import CacheManager
from cyberdrop_dl.managers.client_manager import ClientManager
from cyberdrop_dl.managers.config_manager import ConfigManager
from cyberdrop_dl.managers.db_manager import DBManager
from cyberdrop_dl.managers.download_manager import DownloadManager
from cyberdrop_dl.managers.hash_manager import HashManager
from cyberdrop_dl.managers.live_manager import LiveManager
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.managers.path_manager import PathManager
from cyberdrop_dl.managers.progress_manager import ProgressManager
from cyberdrop_dl.managers.realdebrid_manager import RealDebridManager
from cyberdrop_dl.utils import constants
from cyberdrop_dl.utils.args import ParsedArgs
from cyberdrop_dl.utils.data_enums_classes.supported_domains import SUPPORTED_FORUMS
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.transfer.db_setup import TransitionManager

if TYPE_CHECKING:
    from asyncio import TaskGroup

    from cyberdrop_dl.scraper.scraper import ScrapeMapper


class Manager:
    def __init__(self) -> None:
        self.parsed_args: ParsedArgs = field(init=False)
        self.cache_manager: CacheManager = CacheManager(self)
        self.path_manager: PathManager = field(init=False)
        self.config_manager: ConfigManager = field(init=False)
        self.hash_manager: HashManager = field(init=False)
        self.real_debrid_manager: RealDebridManager = field(init=False)

        self.log_manager: LogManager = field(init=False)
        self.db_manager: DBManager = field(init=False)
        self.client_manager: ClientManager = field(init=False)

        self.download_manager: DownloadManager = field(init=False)
        self.progress_manager: ProgressManager = field(init=False)
        self.live_manager: LiveManager = field(init=False)

        self.first_time_setup: TransitionManager = TransitionManager(self)

        self._loaded_args_config: bool = False
        self._made_portable: bool = False

        self.task_group: TaskGroup = field(init=False)
        self.task_list: list = []
        self.scrape_mapper: ScrapeMapper = field(init=False)

        self.vi_mode: bool = False
        self.start_time: float = perf_counter()
        self.downloaded_data: int = 0
        self.multiconfig: bool = False

    def startup(self) -> None:
        """Startup process for the manager."""

        if isinstance(self.parsed_args, Field):
            self.parsed_args = ParsedArgs.parse_args()

        if not self.parsed_args.cli_only_args.appdata_folder:
            self.first_time_setup.transfer_v4_to_v5()

        self.path_manager = PathManager(self)
        self.path_manager.pre_startup()
        # need pathmanager to get proper appdata location
        self.first_time_setup.transfer_v5_to_new_hashtable()

        self.cache_manager.startup(self.path_manager.cache_folder / "cache.yaml")
        self.config_manager = ConfigManager(self)
        self.config_manager.startup()
        self.args_consolidation()
        self.cache_manager.load_request_cache()
        self.vi_mode = self.config_manager.global_settings_data.ui_options.vi_mode

        self.path_manager.startup()
        self.log_manager = LogManager(self)
        self.adjust_for_simpcity()
        if self.config_manager.loaded_config.casefold() == "all" or self.parsed_args.cli_only_args.multiconfig:
            self.multiconfig = True

    def adjust_for_simpcity(self) -> None:
        """Adjusts settings for SimpCity update."""
        simp_settings_adjusted = self.cache_manager.get("simp_settings_adjusted")
        if not simp_settings_adjusted:
            for config in self.config_manager.get_configs():
                if config != self.config_manager.loaded_config:
                    self.config_manager.change_config(config)
                self.config_manager.settings_data.runtime_options.update_last_forum_post = True
                self.config_manager.write_updated_settings_config()

            rate_limit_options = self.config_manager.global_settings_data.rate_limiting_options
            if rate_limit_options.download_attempts >= 10:
                rate_limit_options.download_attempts = 5
            if rate_limit_options.max_simultaneous_downloads_per_domain > 15:
                rate_limit_options.max_simultaneous_downloads_per_domain = 5
            self.config_manager.write_updated_global_settings_config()
        self.cache_manager.save("simp_settings_adjusted", True)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        """Async startup process for the manager."""
        self.args_logging()

        if not isinstance(self.client_manager, ClientManager):
            self.client_manager = ClientManager(self)
        if not isinstance(self.download_manager, DownloadManager):
            self.download_manager = DownloadManager(self)
        if not isinstance(self.real_debrid_manager, RealDebridManager):
            self.real_debrid_manager = RealDebridManager(self)
        await self.async_db_hash_startup()

        constants.MAX_NAME_LENGTHS["FILE"] = self.config_manager.global_settings_data.general.max_file_name_length
        constants.MAX_NAME_LENGTHS["FOLDER"] = self.config_manager.global_settings_data.general.max_folder_name_length

    async def async_db_hash_startup(self) -> None:
        if not isinstance(self.db_manager, DBManager):
            self.db_manager = DBManager(self, self.path_manager.history_db)
            await self.db_manager.startup()
        if not isinstance(self.hash_manager, HashManager):
            self.hash_manager = HashManager(self)
            await self.hash_manager.startup()
        if not isinstance(self.live_manager, LiveManager):
            self.live_manager = LiveManager(self)
        self.progress_manager = ProgressManager(self)
        self.progress_manager.startup()

    def args_consolidation(self) -> None:
        """Consolidates runtime arguments with config values."""
        cli_config_settings = self.parsed_args.config_settings.model_dump(exclude_unset=True)
        cli_global_settings = self.parsed_args.global_settings.model_dump(exclude_unset=True)

        current_config_settings = self.config_manager.settings_data.model_dump()
        current_global_settings = self.config_manager.global_settings_data.model_dump()

        merged_config_settings = self.merge_dicts(current_config_settings, cli_config_settings)
        merged_global_settings = self.merge_dicts(current_global_settings, cli_global_settings)

        updated_config_settings = ConfigSettings.model_validate(merged_config_settings)
        updated_global_settings = GlobalSettings.model_validate(merged_global_settings)

        self.config_manager.settings_data = updated_config_settings
        self.config_manager.global_settings_data = updated_global_settings
        self.config_manager.deep_scrape = (
            self.parsed_args.config_settings.runtime_options.deep_scrape or self.config_manager.deep_scrape
        )

    def merge_dicts(self, dict1: dict, dict2: dict):
        for key, val in dict1.items():
            if isinstance(val, dict):
                if key in dict2 and isinstance(dict2[key], dict):
                    self.merge_dicts(dict1[key], dict2[key])
            else:
                if key in dict2:
                    dict1[key] = dict2[key]

        for key, val in dict2.items():
            if key not in dict1:
                dict1[key] = val

        return dict1

    def args_logging(self) -> None:
        """Logs the runtime arguments."""
        forum_xf_cookies_provided = {}
        forum_credentials_provided = {}

        auth_data_forums = self.config_manager.authentication_data.forums.model_dump()
        auth_data_others: dict[str, dict] = self.config_manager.authentication_data.model_dump(exclude="forums")

        for forum_name in SUPPORTED_FORUMS:
            forum_xf_cookies_provided[forum_name] = bool(auth_data_forums[f"{forum_name}_xf_user_cookie"])
            forum_credentials_provided[forum_name] = bool(
                auth_data_forums[f"{forum_name}_username"] and auth_data_forums[f"{forum_name}_password"],
            )

        auth_provided = {
            "Forums Credentials": forum_credentials_provided,
            "Forums XF Cookies": forum_xf_cookies_provided,
        }

        for site, auth_entries in auth_data_others.items():
            auth_provided[site] = all(auth_entries.values())

        config_settings = self.config_manager.settings_data.model_copy()
        config_settings.runtime_options.deep_scrape = self.config_manager.deep_scrape
        config_settings = config_settings.model_dump_json(indent=4)
        global_settings = self.config_manager.global_settings_data.model_dump_json(indent=4)

        log("Starting Cyberdrop-DL Process", 10)
        log(f"Running Version: {__version__}", 10)
        log(f"Using Config: {self.config_manager.loaded_config}", 10)
        log(f"Using Config File: {self.config_manager.settings.resolve()}", 10)
        log(f"Using Input File: {self.path_manager.input_file.resolve()}", 10)
        log(f"Using Download Folder: {self.path_manager.download_folder.resolve()}", 10)
        log(f"Using Database File: {self.path_manager.history_db.resolve()}", 10)
        log(f"Using Authentication: \n{json.dumps(auth_provided, indent=4, sort_keys=True)}", 10)
        log(f"Using Settings: \n{config_settings}", 10)
        log(f"Using Global Settings: \n{global_settings}", 10)

    async def close(self) -> None:
        """Closes the manager."""
        await self.db_manager.close()
        if not isinstance(self.client_manager, Field):
            await self.client_manager.close()
        await self.cache_manager.close()
        self.db_manager: DBManager = field(init=False)
        self.cache_manager: CacheManager = field(init=False)
        self.hash_manager: HashManager = field(init=False)

    def validate_all_configs(self) -> None:
        all_configs = self.config_manager.get_configs()
        all_configs.sort()
        if not all_configs:
            return
        for config in all_configs:
            self.config_manager.change_config(config)
