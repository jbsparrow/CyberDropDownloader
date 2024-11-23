from __future__ import annotations

from enum import IntEnum, StrEnum
from pathlib import Path, PurePath

import yaml
from pydantic import BaseModel
from yarl import URL

from cyberdrop_dl.clients.errors import InvalidYamlError

# from cyberdrop_dl.utils.constants import BROWSERS


def save_as_str(dumper: yaml.Dumper, value):
    return dumper.represent_str(str(value))


yaml.add_multi_representer(PurePath, save_as_str)
yaml.add_multi_representer(StrEnum, save_as_str)
yaml.add_multi_representer(IntEnum, int)
yaml.add_representer(URL, save_as_str)


class YamlManager:
    @staticmethod
    def save(file: Path, data: BaseModel | dict) -> None:
        """Saves a dict to a yaml file."""
        if isinstance(data, BaseModel):
            data = data.model_dump()
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("w", encoding="utf8") as yaml_file:
            yaml.dump(data, yaml_file)

    @staticmethod
    def load(file: Path, *, create: bool = False) -> dict:
        """Loads a yaml file and returns it as a dict."""
        if create:
            file.parent.mkdir(parents=True, exist_ok=True)
            if not file.is_file():
                file.touch()
        try:
            with file.open(encoding="utf8") as yaml_file:
                yaml_values = yaml.safe_load(yaml_file.read())
                return yaml_values if yaml_values else {}
        except yaml.constructor.ConstructorError as e:
            raise InvalidYamlError(file, e) from None
