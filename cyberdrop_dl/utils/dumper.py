from __future__ import annotations

import asyncio
import datetime
import enum
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem


class Dumper:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.jsonl_file = manager.path_manager.main_log.with_suffix(".results.jsonl")

    def get_media_items_as_dict(self) -> Generator[dict]:
        for item in self.manager.path_manager.prev_downloads:
            yield convert_to_dict(item)
        for item in self.manager.path_manager.completed_downloads:
            yield convert_to_dict(item)

    async def run(self) -> None:
        await dump_jsonl(self.get_media_items_as_dict(), self.jsonl_file)


def convert_to_dict(media_item: MediaItem) -> dict:
    date = media_item.datetime
    item = asdict(media_item)
    if date:
        item["datetime"] = datetime.datetime.fromtimestamp(date)
    return item


async def dump_jsonl(data: Generator[dict], file: Path) -> None:
    with file.open("w", encoding="utf8") as f:
        for item in data:
            json.dump(item, f, cls=JSONStrEncoder)
            f.write("\n")
            await asyncio.sleep(0)  # required to update the UI, but there's no UI at the moment


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
