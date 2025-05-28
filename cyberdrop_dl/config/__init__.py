from __future__ import annotations

import shutil
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

from pydantic import BaseModel

from cyberdrop_dl import constants
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.utils import yaml
from cyberdrop_dl.utils.apprise import get_apprise_urls

from .auth_model import AuthSettings
from .config_model import ConfigSettings
from .global_model import GlobalSettings

if TYPE_CHECKING:
    from cyberdrop_dl.utils.apprise import AppriseURL
    from cyberdrop_dl.utils.args import ParsedArgs


_DEFAULT_CONFIG_KEY = "default_config"
deep_scrape: bool = False

current_config: Config
appdata: AppData

# re-export current config values for easy access
auth: AuthSettings
settings: ConfigSettings
global_settings: GlobalSettings


class AppData(Path):
    def __init__(self, app_data_path: Path) -> None:
        self.configs_dir = app_data_path / "Configs"
        self.cache_dir = app_data_path / "Cache"
        self.cookies_dir = app_data_path / "Cookies"
        self.default_auth_config_file = self.configs_dir / "authentication.yaml"
        self.global_config_file = self.configs_dir / "global_settings.yaml"
        self.cache_db = self.cache_dir / "request_cache.db"
        self.history_db = self.cache_dir / "cyberdrop.db"

    def mkdirs(self) -> None:
        self.mkdir(parents=True, exist_ok=True)
        for dir in (self.configs_dir, self.cache_dir, self.cookies_dir):
            dir.mkdir(exist_ok=True)


def startup() -> None:
    global appdata
    appdata = AppData(constants.APP_STORAGE)


class Config:
    """Helper class to group a single config, not necessarily the current config"""

    def __init__(self, name: str) -> None:
        self.apprise_urls: list[AppriseURL] = []
        self.folder = appdata.configs_dir / name
        self.apprise_file = self.folder / "apprise.txt"
        self.config_file = self.folder / "settings.yaml"
        auth_override = self.folder / "authentication.yaml"
        if auth_override.is_file():
            self.auth_config_file = auth_override
        else:
            self.auth_config_file = appdata.default_auth_config_file

        self.auth: AuthSettings
        self.settings: ConfigSettings
        self.global_settings: GlobalSettings

    def _load(self) -> None:
        """Read each config module from their respective files

        If a files does not exists, uses the default config and creates it"""
        self.auth = AuthSettings.load_file(self.auth_config_file, "socialmediagirls_username:")
        self.settings = ConfigSettings.load_file(self.config_file, "download_error_urls_filename:")
        self.global_settings = GlobalSettings.load_file(appdata.global_config_file, "Dupe_Cleanup_Options:")
        self.apprise_urls = get_apprise_urls(file=self.apprise_file)

    def _resolve_all_paths(self) -> None:
        self.auth.resolve_paths(self.folder.name)
        self.settings.resolve_paths(self.folder.name)
        self.global_settings.resolve_paths(self.folder.name)


def get_default_config() -> str:
    return cache.get(_DEFAULT_CONFIG_KEY) or "Default"


def save_as_new_config(config: Config) -> None:
    """Creates a new settings config file."""
    assert not config.folder.exists()
    write_updated_config(config)


def write_updated_config(config: Config) -> None:
    """Write updated authentication data."""
    yaml.save(config.auth_config_file, config.auth)
    yaml.save(config.config_file, config.settings)
    yaml.save(appdata.global_config_file, config.global_settings)


def get_all_configs() -> list:
    return sorted(config.name for config in appdata.configs_dir.iterdir() if config.is_dir())


def change_default_config(config_name: str) -> None:
    cache.save(_DEFAULT_CONFIG_KEY, config_name)


def delete_config(config_name: str) -> None:
    all_configs = get_all_configs()
    assert config_name in all_configs
    all_configs.remove(config_name)

    if cache.get(_DEFAULT_CONFIG_KEY) == config_name:
        change_default_config(all_configs[0])

    config_path = appdata.configs_dir / config_name
    shutil.rmtree(config_path)


def load_config(self, config_name: str) -> None:
    global current_config
    current_config = Config(config_name)
    current_config._load()
    current_config._resolve_all_paths()

    for key, value in vars(current_config).items():
        if isinstance(value, BaseModel):
            globals()[key] = value

    self.manager.path_manager.startup()
    sleep(1)
    self.manager.log_manager = LogManager(self.manager)
    sleep(1)
