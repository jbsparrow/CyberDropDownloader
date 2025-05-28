from __future__ import annotations

import shutil
from time import sleep
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from cyberdrop_dl import constants
from cyberdrop_dl.exceptions import InvalidYamlError
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.models import get_model_fields
from cyberdrop_dl.utils import yaml
from cyberdrop_dl.utils.apprise import get_apprise_urls

from .auth_config import AuthSettings
from .config import ConfigSettings
from .global_config import GlobalSettings

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.utils.apprise import AppriseURL
    from cyberdrop_dl.utils.args import ParsedArgs

ModelT = TypeVar("ModelT", bound=BaseModel)

_configs_folder: Path
_auth_config_file: Path
_global_config_file: Path
_current_config: Config
_cli_options: ParsedArgs

# current_config values re-exported
deep_scrape: bool
apprise_urls: list[AppriseURL]
name: str
folder: str
apprise_file: Path
config_file: Path
auth: AuthSettings
settings: ConfigSettings
global_settings: GlobalSettings


def set_root_folders(appdata: Path, cli_options: ParsedArgs) -> None:
    global _auth_config_file, _global_config_file, _configs_folder, _cli_options
    _cli_options = cli_options
    _configs_folder = appdata / "Configs"
    _auth_config_file = _configs_folder / "authentication.yaml"
    _global_config_file = _configs_folder / "global_settings.yaml"
    _cache_folder = constants.APP_STORAGE / "Cache"
    _config_folder = constants.APP_STORAGE / "Configs"
    _cookies_dir = constants.APP_STORAGE / "Cookies"
    _cache_db = _cache_folder / "request_cache.db"
    _history_db = _cache_folder / "cyberdrop.db"


class Config:
    def __init__(self, name: str) -> None:
        self.deep_scrape: bool = False
        self.apprise_urls: list[AppriseURL] = []
        self.folder = _configs_folder / name
        self.apprise_file = self.folder / "apprise.txt"
        self.config_file = self.folder / "settings.yaml"

        self.auth: AuthSettings
        self.settings: ConfigSettings
        self.global_settings: GlobalSettings

    @property
    def auth_config_file(self) -> Path:
        auth_override = self.folder / "authentication.yaml"
        if auth_override.is_file():
            return auth_override
        return _auth_config_file

    def _load(self) -> None:
        _configs_folder.mkdir(parents=True, exist_ok=True)
        self.auth = _load_config_file(self.auth_config_file, AuthSettings, "socialmediagirls_username:")
        self.settings = _load_config_file(self.config_file, ConfigSettings, "download_error_urls_filename:")
        self.global_settings = _load_config_file(_global_config_file, GlobalSettings, "Dupe_Cleanup_Options:")
        self.apprise_urls = get_apprise_urls(file=self.apprise_file)


def get_default_config() -> str:
    return cache.get("default_config") or "Default"


def save_as_new_config(config: Config) -> None:
    """Creates a new settings config file."""
    assert not config.folder.exists()
    write_updated_config(config)


def write_updated_config(config: Config) -> None:
    """Write updated authentication data."""
    yaml.save(config.auth_config_file, config.auth)
    yaml.save(config.config_file, config.settings)
    yaml.save(_global_config_file, config.global_settings)


def get_all_configs() -> list:
    return sorted(config.name for config in _configs_folder.iterdir() if config.is_dir())


def change_default_config(config_name: str) -> None:
    cache.save("default_config", config_name)


def delete_config(config_name: str) -> None:
    all_configs = get_all_configs()
    assert config_name in all_configs
    all_configs.remove(config_name)

    if cache.get("default_config") == config_name:
        change_default_config(all_configs[0])

    config_path = _configs_folder / config_name
    shutil.rmtree(config_path)


def change_current_config(self, config_name: str) -> None:
    global _current_config
    _current_config = Config(config_name)
    _current_config._load()
    _current_config.settings.resolve_paths(config_name)

    for key, value in vars(_current_config).items():
        globals()[key] = value

    self.manager.path_manager.startup()
    sleep(1)
    self.manager.log_manager = LogManager(self.manager)
    sleep(1)

    for path in (_cache_folder, _config_folder, _cookies_dir, _log_folder):
        path.mkdir(parents=True, exist_ok=True)
    _cache_db.touch(exist_ok=True)


def is_in_file(search_value: str, file: Path) -> bool:
    if not file.is_file():
        return False
    try:
        return search_value.casefold() in file.read_text().casefold()
    except Exception as e:
        raise InvalidYamlError(file, e) from e


def _load_config_file(path: Path, model: type[ModelT], update_if_has_string: str) -> ModelT:
    default = model()
    if not path.is_file():
        config = default
        needs_update = True

    else:
        all_fields = get_model_fields(default, exclude_unset=False)
        config = model.model_validate(yaml.load(path))
        set_fields = get_model_fields(config)
        needs_update = all_fields != set_fields or is_in_file(update_if_has_string, path)

    if needs_update:
        yaml.save(path, config)
    return config
