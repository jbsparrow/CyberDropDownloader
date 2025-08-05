from __future__ import annotations

import os
import shutil
from dataclasses import field
from time import sleep
from typing import TYPE_CHECKING

from cyberdrop_dl.config import AuthSettings, ConfigSettings, GlobalSettings
from cyberdrop_dl.exceptions import InvalidYamlError
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.utils import yaml
from cyberdrop_dl.utils.apprise import get_apprise_urls

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.apprise import AppriseURL


class ConfigManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.loaded_config: str = None  # type: ignore

        self.authentication_settings: Path = field(init=False)
        self.settings: Path = field(init=False)
        self.global_settings: Path = field(init=False)
        self.deep_scrape: bool = False
        self.apprise_urls: list[AppriseURL] = []

        self.authentication_data: AuthSettings = field(init=False)
        self.settings_data: ConfigSettings = field(init=False)
        self.global_settings_data: GlobalSettings = field(init=False)

    def startup(self) -> None:
        """Startup process for the config manager."""
        self.loaded_config = self.get_loaded_config()
        cli_config = self.manager.parsed_args.cli_only_args.config
        if cli_config and cli_config.casefold() != "all":
            self.loaded_config = cli_config

        self.settings = self.manager.path_manager.config_folder / self.loaded_config / "settings.yaml"
        self.global_settings = self.manager.path_manager.config_folder / "global_settings.yaml"
        self.authentication_settings = self.manager.path_manager.config_folder / "authentication.yaml"
        auth_override = self.manager.path_manager.config_folder / self.loaded_config / "authentication.yaml"

        if auth_override.is_file():
            self.authentication_settings = auth_override

        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.pydantic_config = self.manager.cache_manager.get("pydantic_config")
        self.load_configs()

    def get_loaded_config(self):
        loaded_config = self.loaded_config or self.get_default_config()
        if not loaded_config or loaded_config.casefold() == "all":
            loaded_config = "Default"
        return loaded_config

    def get_default_config(self):
        return self.manager.cache_manager.get("default_config")

    def load_configs(self) -> None:
        """Loads all the configs."""
        self._load_authentication_config()
        self._load_global_settings_config()
        self._load_settings_config()
        self.apprise_file = self.manager.path_manager.config_folder / self.loaded_config / "apprise.txt"
        self.apprise_urls = get_apprise_urls(file=self.apprise_file)
        self._set_apprise_fixed()
        self._set_pydantic_config()

    @staticmethod
    def get_model_fields(model: BaseModel, *, exclude_unset: bool = True) -> set[str]:
        fields = set()
        default_dict: dict = model.model_dump(exclude_unset=exclude_unset)
        for submodel_name, submodel in default_dict.items():
            for field_name in submodel:
                fields.add(f"{submodel_name}.{field_name}")
        return fields

    def _load_authentication_config(self) -> None:
        """Verifies the authentication config file and creates it if it doesn't exist."""
        needs_update = is_in_file("socialmediagirls_username:", self.authentication_settings)
        posible_fields = self.get_model_fields(AuthSettings(), exclude_unset=False)
        if self.authentication_settings.is_file():
            self.authentication_data = AuthSettings.model_validate(yaml.load(self.authentication_settings))
            set_fields = self.get_model_fields(self.authentication_data)
            if posible_fields == set_fields and not needs_update and self.pydantic_config:
                return

        else:
            self.authentication_data = AuthSettings()

        yaml.save(self.authentication_settings, self.authentication_data)

    def _load_settings_config(self) -> None:
        """Verifies the settings config file and creates it if it doesn't exist."""
        needs_update = is_in_file("download_error_urls_filename:", self.settings)
        posible_fields = self.get_model_fields(ConfigSettings(), exclude_unset=False)
        if self.manager.parsed_args.cli_only_args.config_file:
            self.settings = self.manager.parsed_args.cli_only_args.config_file
            self.loaded_config = "CLI-Arg Specified"

        if self.settings.is_file():
            self.settings_data = ConfigSettings.model_validate(yaml.load(self.settings))
            set_fields = self.get_model_fields(self.settings_data)
            self.deep_scrape = self.settings_data.runtime_options.deep_scrape
            self.settings_data.runtime_options.deep_scrape = False
            if posible_fields == set_fields and not needs_update and self.pydantic_config:
                return
        else:
            self.settings_data = ConfigSettings()
            self.settings_data.files.input_file = (
                self.manager.path_manager.appdata / "Configs" / self.loaded_config / "URLs.txt"
            )
            downloads = self.manager.path_manager.cwd / "Downloads"
            self.settings_data.sorting.sort_folder = downloads / "Cyberdrop-DL Sorted Downloads"
            self.settings_data.files.download_folder = downloads / "Cyberdrop-DL Downloads"
            self.settings_data.logs.log_folder = (
                self.manager.path_manager.appdata / "Configs" / self.loaded_config / "Logs"
            )

        yaml.save(self.settings, self.settings_data)

    def _load_global_settings_config(self) -> None:
        """Verifies the global settings config file and creates it if it doesn't exist."""
        needs_update = is_in_file("Dupe_Cleanup_Options:", self.global_settings)
        posible_fields = self.get_model_fields(GlobalSettings(), exclude_unset=False)
        if self.global_settings.is_file():
            self.global_settings_data = GlobalSettings.model_validate(yaml.load(self.global_settings))
            set_fields = self.get_model_fields(self.global_settings_data)
            if posible_fields == set_fields and not needs_update and self.pydantic_config:
                return
        else:
            self.global_settings_data = GlobalSettings()

        yaml.save(self.global_settings, self.global_settings_data)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def save_as_new_config(self, new_settings: Path, settings_data: ConfigSettings) -> None:
        """Creates a new settings config file."""
        yaml.save(new_settings, settings_data)

    def write_updated_authentication_config(self) -> None:
        """Write updated authentication data."""
        yaml.save(self.authentication_settings, self.authentication_data)

    def write_updated_settings_config(self) -> None:
        """Write updated settings data."""
        yaml.save(self.settings, self.settings_data)

    def write_updated_global_settings_config(self) -> None:
        """Write updated global settings data."""
        yaml.save(self.global_settings, self.global_settings_data)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_configs(self) -> list:
        """Returns a list of all the configs."""
        configs = [config.name for config in self.manager.path_manager.config_folder.iterdir() if config.is_dir()]
        configs.sort()
        return configs

    def change_default_config(self, config_name: str) -> None:
        """Changes the default config."""
        self.manager.cache_manager.save("default_config", config_name)

    def delete_config(self, config_name: str) -> None:
        """Deletes a config."""
        configs = self.get_configs()
        configs.remove(config_name)

        if self.manager.cache_manager.get("default_config") == config_name:
            self.manager.cache_manager.save("default_config", configs[0])

        config = self.manager.path_manager.config_folder / config_name
        shutil.rmtree(config)

    def change_config(self, config_name: str) -> None:
        """Changes the config."""
        self.loaded_config = config_name
        self.startup()

        self.manager.path_manager.startup()
        sleep(1)
        self.manager.log_manager = LogManager(self.manager)
        sleep(1)

    def _set_apprise_fixed(self):
        apprise_fixed = self.manager.cache_manager.get("apprise_fixed")
        if apprise_fixed:
            return
        if os.name == "nt":
            try:
                import win32con  # noqa: F401
            except ImportError:
                pass
            else:
                with self.apprise_file.open("a", encoding="utf8") as f:
                    f.write("windows://\n")
        self.manager.cache_manager.save("apprise_fixed", True)

    def _set_pydantic_config(self):
        if self.pydantic_config:
            return
        self.manager.cache_manager.save("pydantic_config", True)
        self.pydantic_config = True


def is_in_file(search_value: str, file: Path) -> bool:
    if not file.is_file():
        return False
    try:
        return search_value.casefold() in file.read_text().casefold()
    except Exception as e:
        raise InvalidYamlError(file, e) from e
