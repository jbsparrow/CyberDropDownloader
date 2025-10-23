from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_M3U8_SERVER = AbsoluteHttpURL("https://surrit.com/")
_PRIMARY_URL = AbsoluteHttpURL("https://missav.ws")
_COLLECTION_TYPES = "makers", "search", "genres", "labels", "tags"


class Selector:
    UUID = "script:-soup-contains('m3u8|')"
    DATE = "div > span:-soup-contains('Release date:') + time"
    DVD_CODE = "div > span:-soup-contains('Code:') + span"
    NEXT_PAGE = "nav a[rel=next]"
    ITEM = ".grid .thumbnail.group a"


class MissAVCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/...",
        **{name.capitalize(): f"/{name}/<{name.removesuffix('s')}>" for name in _COLLECTION_TYPES},
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    DOMAIN: ClassVar[str] = "missav"
    FOLDER_DOMAIN: ClassVar[str] = "MissAV"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        n_parts = len(scrape_item.url.parts)
        for part in _COLLECTION_TYPES:
            if part in scrape_item.url.parts and n_parts == scrape_item.url.parts.index(part) + 2:
                return await self.collection(scrape_item, part)
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str) -> None:
        name = scrape_item.url.name
        title = self.create_title(f"{name} [{collection_type}]")
        scrape_item.setup_as_album(title)

        async for soup in self.web_pager(scrape_item.url.update_query(page=1), cffi=True):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        canonical_url = _PRIMARY_URL / "en" / scrape_item.url.name
        scrape_item.url = canonical_url
        if await self.check_complete_from_referer(canonical_url):
            return

        soup = await self.request_soup(scrape_item.url, impersonate=True)

        title, date_str = open_graph.title(soup), open_graph.get("video_release_date", soup)
        if dvd_code_tag := soup.select_one(Selector.DVD_CODE):
            title = _fix_title(title, dvd_code_tag)

        if date_str:
            scrape_item.possible_datetime = self.parse_iso_date(date_str)
        elif date_tag := soup.select_one(Selector.DATE):
            scrape_item.possible_datetime = self.parse_iso_date(css.get_attr(date_tag, "datetime"))
        else:
            _ = self.parse_date("")  # Trigger warning

        uuid = _get_uuid(soup)
        m3u8_playlist_url = _M3U8_SERVER / uuid / "playlist.m3u8"
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_playlist_url)
        ext = ".mp4"
        filename = self.create_custom_filename(title, ext, resolution=info.resolution)
        await self.handle_file(m3u8_playlist_url, scrape_item, title, ext, m3u8=m3u8, custom_filename=filename)


def _get_uuid(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, Selector.UUID)
    uuid_joined_parts = js_text.split("m3u8|", 1)[-1].split("|com|surrit", 1)[0]
    uuid_parts = reversed(uuid_joined_parts.split("|"))
    return "-".join(uuid_parts)


def _fix_title(title: str, dvd_code_tag: Tag) -> str:
    dvd_code = css.get_text(dvd_code_tag).upper()
    uncensored = "UNCENSORED" in dvd_code
    leak = "LEAK" in dvd_code
    for trash in ("-UNCENSORED", "-LEAK"):
        dvd_code = dvd_code.replace(trash, "").removesuffix("-")

    title = " ".join(word for word in title.split(" ") if dvd_code not in word.upper())
    full_dvd_code = f"{dvd_code}{(uncensored and '-UNCENSORED') or ''}{(leak and '-LEAK') or ''}"
    return f"{full_dvd_code} {title}"
