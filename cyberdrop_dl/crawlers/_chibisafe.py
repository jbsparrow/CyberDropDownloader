"""ChibiSafe (known as LoliSafe until v4.0.0)

https://github.com/chibisafe/chibisafe
https://chibisafe.moe/docs
https://chibisafe.app/

This is the file host framework used by bunkr, saint, cyberdrop, etc
"""

from __future__ import annotations

import dataclasses
import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.utils.dates import to_timestamp
from cyberdrop_dl.utils.utilities import error_handling_wrapper, type_adapter

if TYPE_CHECKING:
    from cyberdrop_dl.crawlers.crawler import SupportedPaths
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


@dataclasses.dataclass(slots=True)
class File:
    name: str
    url: str
    createdAt: datetime.datetime | None = None  # noqa: N815
    original: str | None = None


class Album(AliasModel):
    id: str = ""
    name: str = Field(validation_alias="title")
    files: list[File]


_parse_file = type_adapter(File)


class ChibiSafeCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/<album_id>",
        "File": "/<file_id>",
    }

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["a", album_id]:
                return await self.album(scrape_item, album_id)
            case [file_id]:
                return await self.file(scrape_item, file_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem, file_id: str) -> None:
        content: dict[str, Any] = await self.request_json(self.PRIMARY_URL / "api/file" / file_id)
        file = _parse_file(content)
        self._handle_file(scrape_item, file)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        content = await self.request_text(self.PRIMARY_URL / "api/album" / album_id)
        album = Album.model_validate_json(content, by_alias=True)
        album.id = album_id
        return await self._handle_album(scrape_item, album)

    async def _handle_album(self, scrape_item: ScrapeItem, album: Album) -> None:
        title = self.create_title(album.name, album.id)
        scrape_item.setup_as_album(title, album_id=album.id)
        results = await self.get_album_results(album.id)

        for file in album.files:
            url = self.parse_url(file.url.removeprefix("null"))
            if self.check_album_results(url, results):
                continue
            new_scrape_item = scrape_item.create_child(url)
            self._handle_file(new_scrape_item, file)
            scrape_item.add_children()

    @error_handling_wrapper
    def _handle_file(self, scrape_item: ScrapeItem, file: File) -> None:
        if scrape_item.possible_datetime is None and file.createdAt:
            scrape_item.possible_datetime = to_timestamp(file.createdAt)
        name = file.original or file.name
        filename, ext = self.get_filename_and_ext(name)
        self.create_task(
            self.handle_file(
                scrape_item.url,
                scrape_item,
                name,
                ext,
                custom_filename=filename,
            )
        )
