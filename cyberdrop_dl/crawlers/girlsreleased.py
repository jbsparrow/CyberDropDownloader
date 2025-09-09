from __future__ import annotations

import dataclasses
import itertools
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper, type_adapter

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://www.girlsreleased.com")


@dataclasses.dataclass(frozen=True, slots=True)
class Set:
    id: str
    date: int
    images: list[list[str]]
    site: str
    name: str | None = dataclasses.field(default=None)

    @property
    def url(self):
        return _PRIMARY_URL / "set" / self.id

    def parse_images(self) -> Generator[Image]:
        for img_data in self.images:
            yield Image(*img_data[3:6])


class Image(NamedTuple):
    url: str
    thumbnail: str
    name: str


_parse_set = type_adapter(Set)


class GirlsReleasedCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Model": "/model/<model_id>/<model_name>",
        "Set": "/set/<set_id>",
        "Site": "/site/<site>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "girlsreleased"
    FOLDER_DOMAIN: ClassVar[str] = "GirlsReleased"

    @property
    def separate_posts(self) -> bool:
        return True

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["set", set_id]:
                return await self.set(scrape_item, set_id)
            case ["site" as category, name]:
                return await self.category(scrape_item, category, name)
            case ["model" as category, _, name]:
                return await self.category(scrape_item, category, name)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def set(self, scrape_item: ScrapeItem, set_id: str) -> None:
        api_url = self.PRIMARY_URL / "api/0.1/set" / set_id
        set_data = (await self.request_json(api_url))["set"]
        self._handle_set(scrape_item, _parse_set(set_data))

    @error_handling_wrapper
    async def category(self, scrape_item: ScrapeItem, category: str, name: str) -> None:
        base_api_url = self.PRIMARY_URL / "api/0.1/sets" / category / name / "page"
        title = self.create_title(f"{name} [{category}]")
        scrape_item.setup_as_profile(title)

        for page in itertools.count(0):
            api_url = base_api_url / str(page)
            sets: list[dict[str, Any]] = (await self.request_json(api_url))["sets"]

            for set_data in sets:
                set_ = _parse_set(set_data)
                new_scrape_item = scrape_item.create_child(set_.url)
                self._handle_set(new_scrape_item, set_)
                scrape_item.add_children()

            if len(sets) < 80:
                break

    def _handle_set(self, scrape_item: ScrapeItem, set_: Set) -> None:
        set_name = set_.name or set_.id
        title = self.create_separate_post_title(set_name, set_.id, set_.date)
        scrape_item.setup_as_album(title, album_id=set_.id)
        scrape_item.possible_datetime = set_.date
        for image in set_.parse_images():
            new_scrape_item = scrape_item.create_child(self.parse_url(image.url))
            self.handle_external_links(new_scrape_item)
            scrape_item.add_children()
