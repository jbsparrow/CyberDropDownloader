from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class Dumper:
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.jsonl_file = manager.path_manager.main_log.with_suffix(".results.jsonl")

    def get_media_items_as_dict(self) -> Generator[dict]:
        for item in self.manager.path_manager.prev_downloads:
            yield asdict(item)
        for item in self.manager.path_manager.completed_downloads:
            yield asdict(item)

    def run(self):
        dump_jsonl(self.get_media_items_as_dict(), self.jsonl_file)


def dump_jsonl(data: Generator[dict], file: Path) -> None:
    with file.open("w", encoding="utf8") as f:
        for item in data:
            json.dump(item, f)
        f.write("\n")
