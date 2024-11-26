from __future__ import annotations

import copy
import shutil
from dataclasses import field
from pathlib import Path
from time import sleep
from typing import TYPE_CHECKING

import yaml

from cyberdrop_dl.clients.errors import InvalidYamlError
from cyberdrop_dl.managers.log_manager import LogManager
from cyberdrop_dl.utils.args.config_definitions import authentication_settings, global_settings, settings

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager
from cyberdrop_dl.utils.data_enums_classes.hash import Hashing


def _match_config_dicts(default: dict, existing: dict) -> dict:
    """Matches the keys of two dicts and returns the new dict with the values of the existing dict."""
    for group in default:
        for key in default[group]:
            if group in existing and key in existing[group]:
                default[group][key] = existing[group][key]
    return copy.deepcopy(default)


# Custom representer function for YAML
def _enum_representer(dumper, data):
    return dumper.represent_int(data.value)


def _save_yaml(file: Path, data: dict) -> None:
    """Saves a dict to a yaml file."""
    file.parent.mkdir(parents=True, exist_ok=True)
    # Register the custom representer
    yaml.add_representer(Hashing, _enum_representer)
    # dump
    with file.open("w") as yaml_file:
        yaml.dump(data, yaml_file)
    pass


def _load_yaml(file: Path) -> dict:
    """Loads a yaml file and returns it as a dict."""
    try:
        with file.open() as yaml_file:
            yaml_values = yaml.load(yaml_file.read(), Loader=yaml.FullLoader)
            return yaml_values if yaml_values else {}
    except yaml.constructor.ConstructorError as e:
        raise InvalidYamlError(file, e) from None


def get_keys(dl: dict | list, keys: list | None = None) -> set:
    keys = keys or []
    if isinstance(dl, dict):
        keys += dl.keys()
        _ = [get_keys(x, keys) for x in dl.values()]
    elif isinstance(dl, list):
        _ = [get_keys(x, keys) for x in dl]
    return set(keys)


class ConfigManager:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.loaded_config: str = field(init=False)

        self.authentication_settings: Path = field(init=False)
        self.settings: Path = field(init=False)
        self.global_settings: Path = field(init=False)

        self.authentication_data: dict = field(init=False)
        self.settings_data: dict = field(init=False)
        self.global_settings_data: dict = field(init=False)

    def startup(self) -> None:
        """Startup process for the config manager."""
        if not isinstance(self.loaded_config, str):
            self.loaded_config = self.manager.cache_manager.get("default_config")
            if not self.loaded_config:
                self.loaded_config = "Default"
            if self.manager.args_manager.load_config_from_args:
                self.loaded_config = self.manager.args_manager.load_config_name

        self.authentication_settings = self.manager.path_manager.config_dir / "authentication.yaml"
        self.global_settings = self.manager.path_manager.config_dir / "global_settings.yaml"
        self.settings = self.manager.path_manager.config_dir / self.loaded_config / "settings.yaml"
        if (self.manager.path_manager.config_dir / self.loaded_config / "authentication.yaml").is_file():
            self.authentication_settings = (
                self.manager.path_manager.config_dir / self.loaded_config / "authentication.yaml"
            )

        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.load_configs()

    def load_configs(self) -> None:
        """Loads all the configs."""
        if self.authentication_settings.is_file():
            self._verify_authentication_config()
        else:
            self.authentication_data = copy.deepcopy(authentication_settings)
            _save_yaml(self.authentication_settings, self.authentication_data)

        if self.global_settings.is_file():
            self._verify_global_settings_config()
        else:
            self.global_settings_data = copy.deepcopy(global_settings)
            _save_yaml(self.global_settings, self.global_settings_data)

        if self.manager.args_manager.config_file:
            self.settings = Path(self.manager.args_manager.config_file)
            self.loaded_config = "CLI-Arg Specified"

        if self.settings.is_file():
            self._verify_settings_config()
        else:
            from cyberdrop_dl.utils import constants

            self.settings_data = copy.deepcopy(settings)
            self.settings_data["Files"]["input_file"] = (
                constants.APP_STORAGE / "Configs" / self.loaded_config / "URLs.txt"
            )
            self.settings_data["Files"]["download_folder"] = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Downloads"
            self.settings_data["Logs"]["log_folder"] = constants.APP_STORAGE / "Configs" / self.loaded_config / "Logs"
            self.settings_data["Logs"]["webhook_url"] = ""
            self.settings_data["Sorting"]["sort_folder"] = constants.DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"
            self.settings_data["Sorting"]["scan_folder"] = None
            self.write_updated_settings_config()

    def return_verified(self, value) -> any:
        if isinstance(value, bool):
            return bool(value)
        if isinstance(value, int):
            return int(value)
        if isinstance(value, str):
            return str(value)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            return dict(value)
        return value

    def _verify_authentication_config(self) -> None:
        """Verifies the authentication config file and creates it if it doesn't exist."""
        default_auth_data = copy.deepcopy(authentication_settings)
        existing_auth_data = _load_yaml(self.authentication_settings)

        if get_keys(default_auth_data) == get_keys(existing_auth_data):
            self.authentication_data = existing_auth_data
            return

        self.authentication_data = _match_config_dicts(default_auth_data, existing_auth_data)
        _save_yaml(self.authentication_settings, self.authentication_data)

    def _verify_settings_config(self) -> None:
        """Verifies the settings config file and creates it if it doesn't exist."""
        default_settings_data = copy.deepcopy(settings)
        existing_settings_data = _load_yaml(self.settings)
        self.settings_data = _match_config_dicts(default_settings_data, existing_settings_data)
        paths = set(
            [
                ("Files", "input_file"),
                ("Files", "download_folder"),
                ("Logs", "log_folder"),
                ("Sorting", "sort_folder"),
                ("Sorting", "scan_folder"),
            ]
        )
        enums = {("Dupe_Cleanup_Options", "hashing"): Hashing}
        for key, value in default_settings_data.items():
            for subkey, subvalue in value.items():
                self.settings_data[key][subkey] = self.return_verified(subvalue)
                if (key, subkey) in paths:
                    path = self.settings_data[key][subkey]
                    if (path == "None" or path is None) and subkey == "scan_folder":
                        self.settings_data[key][subkey] = None
                    else:
                        self.settings_data[key][subkey] = Path(path)

                if (key, subkey) in enums:
                    enum_value = self.settings_data[key][subkey]
                    enum_class = enums[(key, subkey)]
                    if isinstance(enum_value, str):
                        self.settings_data[key][subkey] = enum_class[enum_value]
                    else:
                        self.settings_data[key][subkey] = enum_class(enum_value)

        if get_keys(default_settings_data) == get_keys(existing_settings_data):
            return

        save_data = copy.deepcopy(self.settings_data)
        save_data["Files"]["input_file"] = str(save_data["Files"]["input_file"])
        save_data["Files"]["download_folder"] = str(save_data["Files"]["download_folder"])
        save_data["Logs"]["log_folder"] = str(save_data["Logs"]["log_folder"])
        save_data["Logs"]["webhook_url"] = str(save_data["Logs"]["webhook_url"])
        save_data["Sorting"]["sort_folder"] = str(save_data["Sorting"]["sort_folder"])
        save_data["Sorting"]["scan_folder"] = (
            str(save_data["Sorting"]["scan_folder"])
            if save_data["Sorting"]["scan_folder"] not in ["None", None]
            else None
        )
        _save_yaml(self.settings, save_data)

    def _verify_global_settings_config(self) -> None:
        """Verifies the global settings config file and creates it if it doesn't exist."""
        default_global_settings_data = copy.deepcopy(global_settings)
        existing_global_settings_data = _load_yaml(self.global_settings)
        self.global_settings_data = _match_config_dicts(default_global_settings_data, existing_global_settings_data)

        if get_keys(default_global_settings_data) == get_keys(existing_global_settings_data):
            self.global_settings_data = existing_global_settings_data
            return

        for key, value in default_global_settings_data.items():
            for subkey, subvalue in value.items():
                self.global_settings_data[key][subkey] = self.return_verified(subvalue)

        _save_yaml(self.global_settings, self.global_settings_data)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @staticmethod
    def create_new_config(new_settings: Path, settings_data: dict) -> None:
        """Creates a new settings config file."""
        settings_data["Files"]["input_file"] = (
            str(settings_data["Files"]["input_file"]) if settings_data["Files"]["input_file"] is not None else None
        )
        settings_data["Files"]["download_folder"] = (
            str(settings_data["Files"]["download_folder"])
            if settings_data["Files"]["download_folder"] is not None
            else None
        )
        settings_data["Logs"]["log_folder"] = (
            str(settings_data["Logs"]["log_folder"]) if settings_data["Logs"]["log_folder"] is not None else None
        )
        settings_data["Logs"]["webhook_url"] = (
            str(settings_data["Logs"]["webhook_url"]) if settings_data["Logs"]["webhook_url"] is not None else None
        )
        settings_data["Sorting"]["sort_folder"] = (
            str(settings_data["Sorting"]["sort_folder"])
            if settings_data["Sorting"]["sort_folder"] is not None
            else None
        )
        settings_data["Sorting"]["scan_folder"] = (
            str(settings_data["Sorting"]["scan_folder"])
            if settings_data["Sorting"]["scan_folder"] not in ["None", None]
            else None
        )

        _save_yaml(new_settings, settings_data)

    def write_updated_authentication_config(self) -> None:
        """Write updated authentication data."""
        _save_yaml(self.authentication_settings, self.authentication_data)

    def write_updated_settings_config(self) -> None:
        """Write updated settings data."""
        settings_data = copy.deepcopy(self.settings_data)
        settings_data["Files"]["input_file"] = (
            str(settings_data["Files"]["input_file"]) if settings_data["Files"]["input_file"] is not None else None
        )
        settings_data["Files"]["download_folder"] = (
            str(settings_data["Files"]["download_folder"])
            if settings_data["Files"]["download_folder"] is not None
            else None
        )
        settings_data["Logs"]["log_folder"] = (
            str(settings_data["Logs"]["log_folder"]) if settings_data["Logs"]["log_folder"] is not None else None
        )
        settings_data["Logs"]["webhook_url"] = (
            str(settings_data["Logs"]["webhook_url"]) if settings_data["Logs"]["webhook_url"] is not None else None
        )
        settings_data["Sorting"]["sort_folder"] = (
            str(settings_data["Sorting"]["sort_folder"])
            if settings_data["Sorting"]["sort_folder"] is not None
            else None
        )
        settings_data["Sorting"]["scan_folder"] = (
            str(settings_data["Sorting"]["scan_folder"])
            if settings_data["Sorting"]["scan_folder"] not in ["None", None]
            else None
        )

        _save_yaml(self.settings, settings_data)

    def write_updated_global_settings_config(self) -> None:
        """Write updated global settings data."""
        _save_yaml(self.global_settings, self.global_settings_data)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    def get_configs(self) -> list:
        """Returns a list of all the configs."""
        return [config.name for config in self.manager.path_manager.config_dir.iterdir() if config.is_dir()]

    def change_default_config(self, config_name: str) -> None:
        """Changes the default config."""
        self.manager.cache_manager.save("default_config", config_name)

    def delete_config(self, config_name: str) -> None:
        """Deletes a config."""
        configs = self.get_configs()
        configs.remove(config_name)

        if self.manager.cache_manager.get("default_config") == config_name:
            self.manager.cache_manager.save("default_config", configs[0])

        config = self.manager.path_manager.config_dir / config_name
        shutil.rmtree(config)

    def change_config(self, config_name: str) -> None:
        """Changes the config."""
        self.loaded_config = config_name
        self.startup()

        self.manager.path_manager.startup()
        sleep(1)
        self.manager.log_manager = LogManager(self.manager)
        sleep(1)
