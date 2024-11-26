from __future__ import annotations

import shutil
from dataclasses import field
from time import sleep
from typing import TYPE_CHECKING

from cyberdrop_dl.config_definitions import AuthSettings, ConfigSettings, GlobalSettings
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.utils import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class ConfigManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.loaded_config: str = field(init=False)

        self.authentication_settings: Path = field(init=False)
        self.settings: Path = field(init=False)
        self.global_settings: Path = field(init=False)

        self.authentication_data: AuthSettings = field(init=False)
        self.settings_data: ConfigSettings = field(init=False)
        self.global_settings_data: GlobalSettings = field(init=False)

    def startup(self) -> None:
        """Startup process for the config manager."""
        if not isinstance(self.loaded_config, str):
            self.loaded_config = self.manager.cache_manager.get("default_config")
            if not self.loaded_config:
                self.loaded_config = "Default"
            if self.manager.parsed_args.cli_only_args.config:
                self.loaded_config = self.manager.parsed_args.cli_only_args.config

        self.settings = self.manager.path_manager.config_folder / self.loaded_config / "settings.yaml"
        self.global_settings = self.manager.path_manager.config_folder / "global_settings.yaml"
        self.authentication_settings = self.manager.path_manager.config_folder / "authentication.yaml"
        auth_override = self.manager.path_manager.config_folder / self.loaded_config / "authentication.yaml"

        if auth_override.is_file():
            self.authentication_settings = auth_override

        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.pydantic_config = self.manager.cache_manager.get("pydantic_config")
        self.load_configs()
        if not self.pydantic_config:
            self.pydantic_config = True
            self.manager.cache_manager.save("pydantic_config", True)

    def load_configs(self) -> None:
        """Loads all the configs."""
        self._load_authentication_config()
        self._load_global_settings_config()
        self._load_settings_config()

    def _load_authentication_config(self) -> None:
        """Verifies the authentication config file and creates it if it doesn't exist."""
        posible_fields = AuthSettings.model_fields.keys()
        if self.authentication_settings.is_file():
            self.authentication_data = AuthSettings.model_validate(yaml.load(self.authentication_settings))
            if posible_fields == self.authentication_data.model_fields_set and self.pydantic_config:
                return

        else:
            self.authentication_data = AuthSettings()

        yaml.save(self.authentication_settings, self.authentication_data)

    def _load_settings_config(self) -> None:
        """Verifies the settings config file and creates it if it doesn't exist."""
        posible_fields = ConfigSettings.model_fields.keys()
        if self.manager.parsed_args.cli_only_args.config_file:
            self.settings = self.manager.parsed_args.cli_only_args.config_file
            self.loaded_config = "CLI-Arg Specified"

        if self.settings.is_file():
            self.settings_data = ConfigSettings.model_validate(yaml.load(self.settings))
            if posible_fields == self.settings_data.model_fields_set and self.pydantic_config:
                return
        else:
            from cyberdrop_dl.utils import constants

            self.settings_data = ConfigSettings()
            self.settings_data.files.input_file = constants.APP_STORAGE / "Configs" / self.loaded_config / "URLs.txt"
            self.settings_data.files.download_folder = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Downloads"
            self.settings_data.logs.log_folder = constants.APP_STORAGE / "Configs" / self.loaded_config / "Logs"
            self.settings_data.sorting.sort_folder = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"

        yaml.save(self.settings, self.settings_data)

    def _load_global_settings_config(self) -> None:
        """Verifies the global settings config file and creates it if it doesn't exist."""
        posible_fields = ConfigSettings.model_fields.keys()
        if self.global_settings.is_file():
            self.global_settings_data = GlobalSettings.model_validate(yaml.load(self.global_settings))
            if posible_fields == self.global_settings_data.model_fields_set and self.pydantic_config:
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
        return [config.name for config in self.manager.path_manager.config_folder.iterdir() if config.is_dir()]

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
