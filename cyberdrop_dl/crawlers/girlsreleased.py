from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class GirlsReleasedCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Model": "/model/<model_id>/<model_name>",
        "Set": "/set/<set_id>",
        "Site": "/site/<site>",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://girlsreleased.com")
    DOMAIN = "girlsreleased"
    FOLDER_DOMAIN = "GirlsReleased"

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
        async with self.request_limiter:
            json_resp = await self.client.get_json(self.DOMAIN, api_url)

        self._handle_set(scrape_item, json_resp["set"])

    @error_handling_wrapper
    async def category(self, scrape_item: ScrapeItem, category: str, name: str) -> None:
        api_url = self.PRIMARY_URL / "api/0.1/sets" / category / name / "page"
        title = self.create_title(f"{name} [{category}]")
        scrape_item.setup_as_profile(title)

        for page in itertools.count():
            async with self.request_limiter:
                json_resp = await self.client.get_json(self.DOMAIN, api_url / str(page))

            sets: list[dict[str, Any]] = json_resp["sets"]
            for set_ in sets:
                new_scrape_item = scrape_item.create_child(self.PRIMARY_URL / "set" / set_["id"])
                self._handle_set(new_scrape_item, set_)
                scrape_item.add_children()

            if len(sets) < 80:
                break

    def _handle_set(self, scrape_item: ScrapeItem, set_: dict[str, Any]) -> None:
        set_id, set_date = set_["id"], set_["date"]
        set_name = set_.get("name") or set_id
        title = self.create_separate_post_title(set_name, set_id, set_date)
        scrape_item.setup_as_album(title, album_id=set_id)
        scrape_item.possible_datetime = set_date
        for image in set_["images"]:
            self.handle_external_links(image[3])
            scrape_item.add_children()
