from __future__ import annotations

import asyncio
import json
from dataclasses import Field, field
from time import perf_counter
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel

from cyberdrop_dl import __version__, constants
from cyberdrop_dl.database import Database
from cyberdrop_dl.database.transfer import transfer_v5_db_to_v6
from cyberdrop_dl.managers.cache_manager import CacheManager
from cyberdrop_dl.managers.client_manager import ClientManager
from cyberdrop_dl.managers.config_manager import ConfigManager
from cyberdrop_dl.managers.hash_manager import HashManager
from cyberdrop_dl.managers.live_manager import LiveManager
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.managers.path_manager import PathManager
from cyberdrop_dl.managers.progress_manager import ProgressManager
from cyberdrop_dl.managers.storage_manager import StorageManager
from cyberdrop_dl.utils import ffmpeg
from cyberdrop_dl.utils.args import ParsedArgs, parse_args
from cyberdrop_dl.utils.logger import LogHandler, QueuedLogger, log
from cyberdrop_dl.utils.utilities import close_if_defined, get_system_information

if TYPE_CHECKING:
    from asyncio import TaskGroup
    from collections.abc import Sequence

    from cyberdrop_dl.scraper.scrape_mapper import ScrapeMapper


class AsyncioEvents(NamedTuple):
    SHUTTING_DOWN: asyncio.Event
    RUNNING: asyncio.Event


class Manager:
    def __init__(self, args: Sequence[str] | None = None) -> None:
        if isinstance(args, str):
            args = [args]

        self.parsed_args: ParsedArgs = field(init=False)
        self.cache_manager: CacheManager = CacheManager(self)
        self.path_manager: PathManager = field(init=False)
        self.config_manager: ConfigManager = field(init=False)
        self.hash_manager: HashManager = field(init=False)

        self.log_manager: LogManager = field(init=False)
        self.db_manager: Database = field(init=False)
        self.client_manager: ClientManager = field(init=False)
        self.storage_manager: StorageManager = field(init=False)

        self.progress_manager: ProgressManager = field(init=False)
        self.live_manager: LiveManager = field(init=False)

        self._loaded_args_config: bool = False
        self._made_portable: bool = False

        self.task_group: TaskGroup = field(init=False)
        self.task_list: list = []
        self.scrape_mapper: ScrapeMapper = field(init=False)
        self.current_task: asyncio.Task = field(init=False)

        self.vi_mode: bool = False
        self.start_time: float = perf_counter()
        self.downloaded_data: int = 0
        self.multiconfig: bool = False
        self.loggers: dict[str, QueuedLogger] = {}
        self.args = args
        self.states: AsyncioEvents

        constants.console_handler = LogHandler(level=constants.CONSOLE_LEVEL)

    @property
    def config(self):
        return self.config_manager.settings_data

    @property
    def auth_config(self):
        return self.config_manager.authentication_data

    @property
    def global_config(self):
        return self.config_manager.global_settings_data

    def shutdown(self, from_user: bool = False):
        """ "Shut everything down (something failed or the user used ctrl + q)"""
        if from_user:
            log("Received keyboard interrupt, shutting down...", 30)
        self.states.SHUTTING_DOWN.set()
        self.current_task.cancel()

    def startup(self) -> None:
        """Startup process for the manager."""

        if isinstance(self.parsed_args, Field):
            self.parsed_args = parse_args(self.args)

        self.path_manager = PathManager(self)
        self.path_manager.pre_startup()
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
        self.set_constants()

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
        self.states = AsyncioEvents(asyncio.Event(), asyncio.Event())
        self.args_logging()

        if not isinstance(self.client_manager, ClientManager):
            self.client_manager = ClientManager(self)
            await self.client_manager.startup()
        if not isinstance(self.storage_manager, StorageManager):
            self.storage_manager = StorageManager(self)

        elif self.states.RUNNING.is_set():
            await self.storage_manager.reset()  # Reset total downloaded data if running multiple configs

        await self.async_db_hash_startup()

        constants.MAX_NAME_LENGTHS["FILE"] = self.config_manager.global_settings_data.general.max_file_name_length
        constants.MAX_NAME_LENGTHS["FOLDER"] = self.config_manager.global_settings_data.general.max_folder_name_length

    async def async_db_hash_startup(self) -> None:
        if not isinstance(self.db_manager, Database):
            self.db_manager = Database(
                self.path_manager.history_db,
                self.config.runtime_options.ignore_history,
            )
            await self.db_manager.startup()
        transfer_v5_db_to_v6(self.path_manager.history_db)
        if not isinstance(self.hash_manager, HashManager):
            self.hash_manager = HashManager(self)
            await self.hash_manager.startup()
        if not isinstance(self.live_manager, LiveManager):
            self.live_manager = LiveManager(self)
        if not isinstance(self.progress_manager, ProgressManager):
            self.progress_manager = ProgressManager(self)
            self.progress_manager.startup()

    def process_additive_args(self) -> None:
        cli_general_options = self.parsed_args.global_settings.general
        cli_ignore_options = self.parsed_args.config_settings.ignore_options
        config_ignore_options = self.config_manager.settings_data.ignore_options
        config_general_options = self.config_manager.global_settings_data.general

        add_or_remove_lists(cli_ignore_options.skip_hosts, config_ignore_options.skip_hosts)
        add_or_remove_lists(cli_ignore_options.only_hosts, config_ignore_options.only_hosts)
        add_or_remove_lists(cli_general_options.disable_crawlers, config_general_options.disable_crawlers)

    def args_consolidation(self) -> None:
        """Consolidates runtime arguments with config values."""
        self.process_additive_args()

        conf = merge_models(self.config_manager.settings_data, self.parsed_args.config_settings)
        global_conf = merge_models(self.config_manager.global_settings_data, self.parsed_args.global_settings)
        deep_scrape = self.parsed_args.config_settings.runtime_options.deep_scrape or self.config_manager.deep_scrape

        self.config_manager.settings_data = conf
        self.config_manager.global_settings_data = global_conf
        self.config_manager.deep_scrape = deep_scrape

    def args_logging(self) -> None:
        """Logs the runtime arguments."""
        auth_data: dict[str, dict] = self.config_manager.authentication_data.model_dump()
        auth_provided = {}

        for site, auth_entries in auth_data.items():
            auth_provided[site] = all(auth_entries.values())

        config_settings = self.config_manager.settings_data.model_copy()
        config_settings.runtime_options.deep_scrape = self.config_manager.deep_scrape
        config_settings = config_settings.model_dump_json(indent=4)
        global_settings = self.config_manager.global_settings_data.model_dump_json(indent=4)
        cli_only_args = self.parsed_args.cli_only_args.model_dump_json(indent=4)
        system_info = get_system_information()

        args_info = (
            "Starting Cyberdrop-DL Process",
            f"Running Version: {__version__}",
            f"System Info: {system_info}",
            f"Using Config: {self.config_manager.loaded_config}",
            f"Using Config File: {self.config_manager.settings}",
            f"Using Input File: {self.path_manager.input_file}",
            f"Using Download Folder: {self.path_manager.download_folder}",
            f"Using Database File: {self.path_manager.history_db}",
            f"Using CLI only options: {cli_only_args}",
            f"Using Authentication: \n{json.dumps(auth_provided, indent=4, sort_keys=True)}",
            f"Using Settings: \n{config_settings}",
            f"Using Global Settings: \n{global_settings}",
            f"Using ffmpeg version: {ffmpeg.get_ffmpeg_version()}",
            f"Using ffprobe version: {ffmpeg.get_ffprobe_version()}",
        )
        log("\n".join(args_info))

    async def async_db_close(self) -> None:
        "Partial shutdown for managers used for hash directory scanner"
        self.db_manager = await close_if_defined(self.db_manager)
        self.hash_manager = constants.NOT_DEFINED
        self.progress_manager.hash_progress.reset()

    async def close(self) -> None:
        """Closes the manager."""
        self.states.RUNNING.clear()

        await self.async_db_close()

        self.client_manager = await close_if_defined(self.client_manager)
        self.storage_manager = await close_if_defined(self.storage_manager)
        self.cache_manager = await close_if_defined(self.cache_manager)

        while self.loggers:
            _, queued_logger = self.loggers.popitem()
            queued_logger.stop()

    def validate_all_configs(self) -> None:
        all_configs = self.config_manager.get_configs()
        all_configs.sort()
        if not all_configs:
            return
        for config in all_configs:
            self.config_manager.change_config(config)

    def set_constants(self) -> None:
        """
        rewrite constants after config/arg manager have loaded
        """
        constants.DISABLE_CACHE = self.parsed_args.cli_only_args.disable_cache


def add_or_remove_lists(cli_values: list[str], config_values: list[str]) -> None:
    exclude = {"+", "-"}
    if cli_values:
        if cli_values[0] == "+":
            new_values_set = set(config_values + cli_values)
            cli_values.clear()
            cli_values.extend(sorted(new_values_set - exclude))
        elif cli_values[0] == "-":
            new_values_set = set(config_values) - set(cli_values)
            cli_values.clear()
            cli_values.extend(sorted(new_values_set - exclude))


def merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    for key, val in dict1.items():
        if isinstance(val, dict):
            if key in dict2 and isinstance(dict2[key], dict):
                merge_dicts(dict1[key], dict2[key])
        else:
            if key in dict2:
                dict1[key] = dict2[key]

    for key, val in dict2.items():
        if key not in dict1:
            dict1[key] = val

    return dict1


M = TypeVar("M", bound=BaseModel)


def merge_models(default: M, new: M) -> M:
    default_dict = default.model_dump()
    new_dict = new.model_dump(exclude_unset=True)

    updated_dict = merge_dicts(default_dict, new_dict)
    return default.model_validate(updated_dict)
