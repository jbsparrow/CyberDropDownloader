from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


MEDIA_INFO_JS_SELECTOR = "script:contains('__fileurl')"
PRIMARY_BASE_DOMAIN = URL("https://motherless.com")
ITEM_SELECTOR = "div.thumb-container a.img-container"
ITEM_TITLE_SELECTOR = "div.media-meta-title"
GALLERY_TITLE_SELECTOR = "div.gallery-title > h2"
GROUP_TITLE_SELECTOR = "div.group-bio > h1"
ITEM_GALLERY_TITLE_SELECTOR = "div.gallery-captions > a.gallery-data"
NOT_FOUND_TEXTS = "The page you're looking for cannot be found", "File not Found. Nothing to see here"
INCLUDE_ID_IN_FILENAME = True


class MediaInfo(NamedTuple):
    type: str
    url: str


class MotherlessCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN
    next_page_selector = "div.pagination_link > a[rel=next]"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "motherless", "Motherless")
        self.request_limiter = AsyncLimiter(2, 1)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem, collection_id: str = "") -> None:
        """Determines where to send the scrape item based on the url."""
        item_id = collection_id or scrape_item.url.name
        is_gallery_homepage = scrape_item.url.name.startswith("G") and len(scrape_item.url.parts) == 2
        is_group_homepage = "g" in scrape_item.url.parts and len(scrape_item.url.parts) == 3

        if "gi" in scrape_item.url.parts:  # group images
            return await self.collection_items(scrape_item, "images", item_id)
        if "gv" in scrape_item.url.parts:  # group videos
            return await self.collection_items(scrape_item, "videos", item_id)
        if is_group_homepage or is_gallery_homepage:  # gallery or group
            return await self.collection(scrape_item)
        return await self.media(scrape_item)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        group_id = scrape_item.url.name
        gallery_id = group_id.removeprefix("G")
        media_types = "images", "videos"
        is_group = "g" in scrape_item.url.parts
        if not is_group and gallery_id.startswith("G"):  # No support for subgalleries
            raise ScrapeError(422)

        for prefix in ("I", "V"):
            gallery_id = gallery_id.removeprefix(prefix)

        if is_group:
            new_urls = [PRIMARY_BASE_DOMAIN / part / group_id for part in ("gi", "gv")]

        else:
            new_urls = [PRIMARY_BASE_DOMAIN / f"{part}{gallery_id}" for part in ("GI", "GV")]

        collection_id = group_id if is_group else gallery_id
        for media_type, url in zip(media_types, new_urls, strict=True):
            new_scrape_item = scrape_item.create_child(url)
            await self.collection_items(new_scrape_item, media_type, collection_id)

    @error_handling_wrapper
    async def collection_items(
        self, scrape_item: ScrapeItem, media_type: Literal["videos", "images"], collection_id: str | None = None
    ) -> None:
        title = ""
        async for soup in self.web_pager(scrape_item):
            check_soup(soup)
            if not title:
                title_tag = soup.select_one(GALLERY_TITLE_SELECTOR) or soup.select_one(GROUP_TITLE_SELECTOR)
                title: str = title_tag.get_text(strip=True)  # type: ignore
                title = self.create_title(title, collection_id)
                scrape_item.setup_as_album(title, album_id=collection_id)
                scrape_item.add_to_parent_title(media_type)

            for item in soup.select(ITEM_SELECTOR):
                link_str: str = item.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        media_id = scrape_item.url.parts[-1]
        canonical_url = PRIMARY_BASE_DOMAIN / media_id

        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        check_soup(soup)
        media_info = self.process_media_soup(scrape_item, soup)
        link = self.parse_url(media_info.url)
        scrape_item.url = canonical_url

        title: str = soup.select_one(ITEM_TITLE_SELECTOR).get_text(strip=True)  # type: ignore
        filename, ext = get_filename_and_ext(link.name)
        custom_filename = Path(title).with_suffix(ext)
        if INCLUDE_ID_IN_FILENAME:
            custom_filename = f"{custom_filename.stem} [{media_id}]{ext}"
        custom_filename, _ = get_filename_and_ext(str(custom_filename))
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def process_media_soup(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> MediaInfo:
        media_info = get_media_info(soup)
        if media_info.type == "gallery":
            raise ScrapeError(422)

        n_parts = len(scrape_item.url.parts)
        from_gallery = n_parts > 2 and scrape_item.url.parts[1].startswith("G")
        from_group = n_parts > 3 and "g" in scrape_item.url.parts
        if not (from_gallery or from_group):
            return media_info

        parent_id = scrape_item.url.parts[2] if from_group else scrape_item.url.parts[1]
        parent_title = ""
        title_tag = soup.select_one(ITEM_GALLERY_TITLE_SELECTOR)
        if from_gallery:
            parent_id = parent_id.removeprefix("G")
            title_tag = soup.select_one(GROUP_TITLE_SELECTOR)

        if title_tag:
            parent_title: str = title_tag.get("title") if from_gallery else title_tag.get_text(strip=True)  # type: ignore

        parent_path = parent_id if from_gallery else f"g/{parent_id}"
        parent_url = PRIMARY_BASE_DOMAIN / parent_path
        if parent_url not in scrape_item.parents and parent_title:
            scrape_item.parents.append(parent_url)
            title = self.create_title(parent_title, parent_id)
            scrape_item.setup_as_album(title, album_id=parent_id)
            scrape_item.add_to_parent_title(f"{media_info.type}s")

        return media_info


def check_soup(soup: BeautifulSoup) -> None:
    soup_str = str(soup)
    if any(p in soup_str for p in NOT_FOUND_TEXTS):
        raise ScrapeError(404)
    if "The content you are trying to view is for friends only" in soup_str:
        raise ScrapeError(401)


def get_media_info(soup: BeautifulSoup) -> MediaInfo:
    media_js = soup.select_one(MEDIA_INFO_JS_SELECTOR)
    js_text = media_js.text if media_js else None
    if not js_text:
        return MediaInfo("gallery", "")
    media_type = js_text.split("__mediatype", 1)[-1].split("=", 1)[-1].split(",", 1)[0].strip()
    url = js_text.split("__fileurl", 1)[-1].split("=", 1)[-1].split(";", 1)[0].strip()
    parts = remove_quotes(media_type.lower()), remove_quotes(url)
    return MediaInfo(*parts)


def remove_quotes(text: str) -> str:
    return text.removeprefix("'").removesuffix("'").removeprefix('"').removesuffix('"')
