from __future__ import annotations

import shutil
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

from cyberdrop_dl import constants, env
from cyberdrop_dl.utils.apprise import get_apprise_urls

from .auth_model import AuthSettings
from .config_model import ConfigSettings
from .global_model import GlobalSettings

if TYPE_CHECKING:
    from cyberdrop_dl.utils.apprise import AppriseURL
    from cyberdrop_dl.utils.args import ParsedArgs

__all__ = [
    "AuthSettings",
    "ConfigSettings",
    "GlobalSettings",
]

deep_scrape: bool = False

current_config: Config
cli: ParsedArgs
appdata: AppData

# re-export current config values for easy access
auth: AuthSettings
settings: ConfigSettings
global_settings: GlobalSettings


def startup() -> None:
    global appdata, cli
    from cyberdrop_dl.utils.args import parse_args

    cli = parse_args()

    if env.RUNNING_IN_IDE and Path.cwd().name == "cyberdrop_dl":
        """This is for testing purposes only"""
        constants.DEFAULT_APP_STORAGE = Path("../AppData")
        constants.DEFAULT_DOWNLOAD_STORAGE = Path("../Downloads")

    appdata_path = cli.cli_only_args.appdata_folder or constants.DEFAULT_APP_STORAGE
    appdata = AppData(appdata_path.resolve())
    appdata.mkdirs()
    # cache.startup(appdata.cache_file)
    load_config(get_default_config())
    settings.logs._delete_old_logs_and_folders(constants.STARTUP_TIME)


class AppData(Path):
    def __init__(self, app_data_path: Path) -> None:
        self.configs_dir = app_data_path / "Configs"
        self.cache_dir = app_data_path / "Cache"
        self.cookies_dir = app_data_path / "Cookies"
        self.cache_file = self.cache_dir / "cache.yaml"
        self.default_auth_config_file = self.configs_dir / "authentication.yaml"
        self.global_config_file = self.configs_dir / "global_settings.yaml"
        self.cache_db = self.cache_dir / "request_cache.db"
        self.history_db = self.cache_dir / "cyberdrop.db"

    def mkdirs(self) -> None:
        for dir in (self.configs_dir, self.cache_dir, self.cookies_dir):
            dir.mkdir(parents=True, exist_ok=True)


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

    @staticmethod
    def build(name: str, auth: AuthSettings, settings: ConfigSettings, global_settings: GlobalSettings) -> Config:
        self = Config(name)
        self.auth = auth
        self.settings = settings
        self.global_settings = global_settings
        self.apprise_urls = get_apprise_urls(file=self.apprise_file)
        return self

    @staticmethod
    def new_empty_config(name: str) -> Config:
        assert name not in get_all_configs()
        self = Config(name)
        self._load()
        return self

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

    def _all_settings(self) -> tuple[ConfigSettings, AuthSettings, GlobalSettings]:
        return self.settings, self.auth, self.global_settings

    def write_updated_config(self) -> None:
        """Writes config to disk."""
        self.auth.save_to_file(self.auth_config_file)
        self.settings.save_to_file(self.config_file)
        self.global_settings.save_to_file(appdata.global_config_file)


def get_default_config() -> str:
    ...
    # return cache.get(cache.DEFAULT_CONFIG_KEY) or "Default"


def get_all_configs() -> list:
    return sorted(config.name for config in appdata.configs_dir.iterdir() if config.is_dir())


def set_default_config(config_name: str) -> None:
    ...
    # cache.save(cache.DEFAULT_CONFIG_KEY, config_name)


def delete_config(config_name: str) -> None:
    all_configs = get_all_configs()
    assert config_name in all_configs
    assert len(all_configs) > 1
    assert config_name != current_config.folder.name
    all_configs.remove(config_name)

    # if cache.get(cache.DEFAULT_CONFIG_KEY) == config_name:
    #    set_default_config(all_configs[0])

    config_path = appdata.configs_dir / config_name
    shutil.rmtree(config_path)


def load_config(config_name: str) -> None:
    global current_config, auth, global_settings, settings
    assert config_name
    current_config = Config(config_name)
    current_config._load()
    current_config._resolve_all_paths()
    settings, auth, global_settings = current_config._all_settings()
    settings.logs._set_output_filenames(constants.STARTUP_TIME)

    sleep(1)
