from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel

from cyberdrop_dl.clients.errors import InvalidYamlError

if TYPE_CHECKING:
    from pathlib import Path


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
                yaml_values = yaml.load(yaml_file.read(), Loader=yaml.FullLoader)
                return yaml_values if yaml_values else {}
        except yaml.constructor.ConstructorError as e:
            raise InvalidYamlError(file, e) from None
