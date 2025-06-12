from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, TypeAlias, TypeGuard, TypeVar

from pydantic import BaseModel

from cyberdrop_dl.utils.dumper import JSONStrEncoder
from cyberdrop_dl.utils.utilities import Dataclass, get_download_path

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.crawlers.crawler import Crawler
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

_Metadata: TypeAlias = BaseModel | Dataclass | dict[str, Any]
_MetadataT = TypeVar("_MetadataT", bound=_Metadata | str)


def make_factory(crawler: Crawler, filename: str, metadata_cls: type[_MetadataT]) -> SideCardFactory[_MetadataT]:
    return SideCardFactory(crawler.manager, crawler.FOLDER_DOMAIN, filename, metadata_cls)


class SideCardFactory(Generic[_MetadataT]):
    def __init__(self, manager: Manager, folder_domain: str, filename: str, metadata_cls: type[_MetadataT]) -> None:
        self.FOLDER_DOMAIN = folder_domain
        self.manager = manager
        self.filename = filename
        self.metadata_cls = metadata_cls

    def new(self, scrape_item: ScrapeItem) -> MetadataSideCard[_MetadataT]:
        file_path = get_download_path(self.manager, scrape_item, self.FOLDER_DOMAIN) / self.filename
        return MetadataSideCard(self, file_path)

    __call__ = new


class MetadataSideCard(Generic[_MetadataT]):
    def __init__(self, side_card: SideCardFactory, file_path: Path) -> None:
        self.sidecard = side_card
        self.path = file_path

    async def save(self, content: _MetadataT | str) -> None:
        if isinstance(content, BaseModel):
            content = content.model_dump_json(indent=4)
        elif isinstance(content, Dataclass):
            content = asdict(content)
        if isinstance(content, dict):
            content = json.dumps(content, indent=4, ensure_ascii=False, cls=JSONStrEncoder)

        assert isinstance(content, str)
        await save_to_file(content, self.path)

    async def read(self) -> _MetadataT | None:
        if content := await read_from_file(self.path):
            if isinstance(self.sidecard.metadata_cls, str):
                return content  # type: ignore
            if issubclass(self.sidecard.metadata_cls, BaseModel):
                return self.sidecard.metadata_cls.model_validate_json(content, by_alias=True, by_name=True)  # type: ignore
            if is_dataclass(self.sidecard.metadata_cls):
                return self.sidecard.metadata_cls(**json.loads(content))  # type: ignore
            raise ValueError


async def save_to_file(content: str, path: Path) -> None:
    def save() -> None:
        if not path.is_file():
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text(content, encoding="utf8")

    return await asyncio.to_thread(save)


async def read_from_file(path: Path) -> str | None:
    def read() -> None:
        try:
            path.read_text(encoding="utf8")
        except OSError:
            pass

    return await asyncio.to_thread(read)


def is_namedtuple_instance(obj: object) -> TypeGuard[NamedTuple]:
    obj_t = type(obj)
    bases = obj_t.__bases__
    if len(bases) != 1 or bases[0] is tuple:
        return False
    fields = getattr(obj_t, "_fields", None)
    if not fields or isinstance(fields, tuple):
        return False
    return all(type(n) is str for n in fields)
