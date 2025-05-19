from __future__ import annotations

import datetime
import enum
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.managers.manager import Manager


KEYS_TO_REMOVE = "file_lock_reference_name", "task_id"
KEYS_TO_REPLACE = {"current_attempt": "attempts"}


class Dumper:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.jsonl_file = manager.path_manager.main_log.with_suffix(".results.jsonl")

    def get_media_items_as_dict(self) -> Generator[dict]:
        for item in self.manager.path_manager.prev_downloads:
            yield convert_to_dict(item)
        for item in self.manager.path_manager.completed_downloads:
            yield convert_to_dict(item)

    def run(self) -> None:
        dump_jsonl(self.get_media_items_as_dict(), self.jsonl_file)


def convert_to_dict(media_item: MediaItem) -> dict:
    date = media_item.datetime
    item = asdict(media_item)
    if date and isinstance(date, int):
        item["datetime"] = datetime.datetime.fromtimestamp(date)
    for key, new_key in KEYS_TO_REPLACE.items():
        item[new_key] = item[key]
        del item[key]
    return {k: v for k, v in item.items() if k not in KEYS_TO_REMOVE}


def dump_jsonl(data: Generator[dict], file: Path) -> None:
    with file.open("w", encoding="utf8") as f:
        for item in data:
            json.dump(item, f, cls=JSONStrEncoder, ensure_ascii=False)
            f.write("\n")


class JSONStrEncoder(json.JSONEncoder):
    """Serialize incompatible objects as str"""

    def default(self, obj: Any) -> str:
        if isinstance(obj, datetime.datetime):
            obj = obj.isoformat()
        if isinstance(obj, enum.Enum):
            obj = obj.value
        if isinstance(obj, set):
            obj = sorted(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)
