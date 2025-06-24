from __future__ import annotations

import random
from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import LoginError, ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://nhentai.net/")
API_ENTRYPOINT = PRIMARY_URL / "api/gallery/"
EXT_MAP = {"a": ".avif", "g": ".gif", "j": ".jpg", "p": ".png", "w": ".webp"}
COLLECTION_PARTS = "favorites", "tag", "search", "parody", "group", "character", "artist"
ITEM_SELECTOR = "div.gallery > a"
COLLECTION_TITLE_SELECTOR = "div#content > h1"
LOGIN_PAGE_SELECTOR = "input.id_username_or_email"


class NHentaiCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Collections": ("favorites", "tag", "search", "parody", "group", "character", "artist"),
        "Gallery": "/g/<gallery_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a.next"
    DOMAIN: ClassVar[str] = "nhentai.net"
    FOLDER_DOMAIN: ClassVar[str] = "nHentai"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(4, 1)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in COLLECTION_PARTS):
            return await self.collection(scrape_item)
        if "g" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        title = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title_tag = soup.select_one(COLLECTION_TITLE_SELECTOR)
                if not title_tag:
                    raise ScrapeError(422)

                collection_type = next((part for part in COLLECTION_PARTS if part in scrape_item.url.parts), None)
                assert collection_type
                if collection_type == "favorites":
                    if soup.select_one(LOGIN_PAGE_SELECTOR):
                        raise LoginError("No cookies provided to download favorites")

                    for span in soup.select("span"):
                        span.decompose()

                else:
                    title_tag = css.select_one(soup, "span.name")
                    title = f" [{collection_type}]"

                title: str = title_tag.get_text(strip=True) + title
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name
        api_url = API_ENTRYPOINT / gallery_id
        async with self.request_limiter:
            json_resp: dict = await self.client.get_json(self.DOMAIN, api_url)

        log_debug(json_resp)
        titles: dict[str, str] = json_resp["title"]
        title: str = titles.get("english") or titles.get("japanese") or titles["pretty"]
        title = self.create_title(title, gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        scrape_item.possible_datetime = json_resp["upload_date"]

        n_images: int = json_resp["num_pages"]
        padding = max(3, len(str(n_images)))
        for index, link in get_image_urls(json_resp):
            filename, ext = self.get_filename_and_ext(link.name)
            custom_filename = self.create_custom_filename(str(index).zfill(padding), ext)
            await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_image_urls(json_resp: dict) -> Generator[tuple[int, AbsoluteHttpURL]]:
    media_id: str = json_resp["media_id"]
    for index, info in enumerate(json_resp["images"]["pages"], 1):
        ext = EXT_MAP.get(info["t"]) or ".jpg"
        cdn = random.randint(1, 4)
        yield index, AbsoluteHttpURL(f"https://i{cdn}.nhentai.net/galleries/{media_id}/{index}{ext}")
