from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selector:
    ITEM = "div.gallery > a"
    COLLECTION_TITLE = "span.name"
    FAVORITES_TITLE = "div#content > h1"
    LOGIN_PAGE = "input.id_username_or_email"


class NHentaiCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Collections": (
            "favorites",
            "tag",
            "search",
            "parody",
            "group",
            "character",
            "artist",
        ),
        "Gallery": "/g/<gallery_id>",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://nhentai.net/")
    NEXT_PAGE_SELECTOR = "a.next"
    DOMAIN = "nhentai.net"
    FOLDER_DOMAIN = "nHentai"
    _RATE_LIMIT = 4, 1

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["favorites" | "tag" | "search" | "parody" | "group" | "character" | "artist" as type_, _]:
                return await self.collection(scrape_item, type_)
            case ["g", _]:
                return await self.gallery(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            if not title:
                if collection_type == "favorites":
                    title_tag = css.select_one(soup, Selector.FAVORITES_TITLE)
                    if soup.select_one(Selector.LOGIN_PAGE):
                        raise LoginError("No cookies provided to download favorites")

                    css.decompose(title_tag, "span")

                else:
                    title_tag = css.select_one(soup, Selector.COLLECTION_TITLE)
                    title = f" [{collection_type}]"

                title = self.create_title(title_tag.get_text(strip=True) + title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name
        api_url = self.PRIMARY_URL / "api/gallery" / gallery_id
        json_resp: dict[str, Any] = await self.request_json(api_url, impersonate=True)

        titles: dict[str, str] = json_resp["title"]
        title: str = titles.get("english") or titles.get("japanese") or titles["pretty"]
        scrape_item.setup_as_album(self.create_title(title, gallery_id), album_id=gallery_id)
        scrape_item.possible_datetime = json_resp["upload_date"]

        padding = max(3, len(str(json_resp["num_pages"])))
        for index, link in _gen_image_urls(json_resp):
            filename = self.create_custom_filename(str(index).zfill(padding), link.suffix)
            self.create_task(self.handle_file(link, scrape_item, link.name, custom_filename=filename))
            scrape_item.add_children()


def _gen_image_urls(json_resp: dict[str, Any]) -> Generator[tuple[int, AbsoluteHttpURL]]:
    media_id: str = json_resp["media_id"]
    for index, page in enumerate(json_resp["images"]["pages"], 1):
        ext = {
            "a": ".avif",
            "g": ".gif",
            "j": ".jpg",
            "p": ".png",
            "w": ".webp",
        }.get(page["t"], ".jpg")
        cdn = random.randint(1, 4)
        yield index, AbsoluteHttpURL(f"https://i{cdn}.nhentai.net/galleries/{media_id}/{index}{ext}")
