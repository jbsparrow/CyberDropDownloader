from __future__ import annotations

from dataclasses import field
from pathlib import Path
from typing import Any, Dict, TYPE_CHECKING

import yaml
import json

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def _save_yaml(file: Path, data: Dict) -> None:
    """Saves a dict to a yaml file"""
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, 'w') as yaml_file:
        yaml.dump(data, yaml_file)

def _save_json(file: Path, data: Dict) -> None:
    """Saves a dict to a yaml file"""
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, 'w') as json_file:
        json.dump(data, json_file)

def _load_yaml(file: Path) -> Dict:
    """Loads a yaml file and returns it as a dict"""
    with open(file, 'r') as yaml_file:
        return yaml.load(yaml_file.read(), Loader=yaml.FullLoader)


def _load_json(file: Path) -> Dict:
    """Loads a json file and returns it as a dict"""
    with open(file, 'r') as json_file:
        return json.loads(json_file.read())
class CacheManager:
    def __init__(self, manager: 'Manager',backend:str="yaml"):
        self.manager = manager

        self.cache_file: Path = field(init=False)
        self._cache = {}
        self.backend=backend

    def startup(self, cache_file: Path) -> None:
        """Ensures that the cache file exists"""
        self.cache_file = cache_file
        if not self.cache_file.is_file():
            self.save('default_config', "Default")

        self.load()
        if self.manager.args_manager.appdata_dir:
            self.save('first_startup_completed', True)

    def load(self) -> None:
        """Loads the cache file into memory"""
        if self.backend=="yaml":
            self._cache = _load_yaml(self.cache_file)
        else:
            self._cache = _load_json(self.cache_file)


    def get(self, key: str) -> Any:
        """Returns the value of a key in the cache"""
        return self._cache.get(key, None)

    def save(self, key: str, value: Any) -> None:
        """Saves a key and value to the cache"""
        self._cache[key] = value
        self.update()

    def remove(self, key: str) -> None:
        """Removes a key from the cache"""
        if key in self._cache:
            del self._cache[key]
            self.update()
    def update(self) -> None:
        """Updates cache with new values/changes"""
        if self.backend=="yaml":
             _save_yaml(self.cache_file, self._cache)
        else:
            _save_json(self.cache_file, self._cache)
