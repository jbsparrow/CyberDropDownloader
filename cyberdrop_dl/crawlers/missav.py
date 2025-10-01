from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


M3U8_SERVER = AbsoluteHttpURL("https://surrit.com/")
PRIMARY_URL = AbsoluteHttpURL("https://missav.ws")
DATE_SELECTOR = "div > span:-soup-contains('Release date:') + time"
DVD_CODE_SELECTOR = "div > span:-soup-contains('Code:') + span"


class MissAVCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": "/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "missav"
    FOLDER_DOMAIN: ClassVar[str] = "MissAV"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        canonical_url = PRIMARY_URL / "en" / scrape_item.url.name
        scrape_item.url = canonical_url
        if await self.check_complete_from_referer(canonical_url):
            return

        soup = await self.request_soup(scrape_item.url, impersonate=True)

        title, date_str = open_graph.title(soup), open_graph.get("video_release_date", soup)
        if dvd_code_tag := soup.select_one(DVD_CODE_SELECTOR):
            title = fix_title(title, dvd_code_tag)

        if date_str:
            scrape_item.possible_datetime = self.parse_iso_date(date_str)
        elif date_tag := soup.select_one(DATE_SELECTOR):
            scrape_item.possible_datetime = self.parse_date(css.get_attr(date_tag, "datetime"))
        else:
            _ = self.parse_date("")  # Trigger warning

        uuid = get_uuid(soup)
        m3u8_playlist_url = M3U8_SERVER / uuid / "playlist.m3u8"
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_playlist_url)
        ext = ".mp4"
        filename = self.create_custom_filename(title, ext, resolution=info.resolution)
        await self.handle_file(m3u8_playlist_url, scrape_item, filename, ext, m3u8=m3u8)


def get_uuid(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, "script:-soup-contains('m3u8|')")
    uuid_joined_parts = js_text.split("m3u8|", 1)[-1].split("|com|surrit", 1)[0]
    uuid_parts = reversed(uuid_joined_parts.split("|"))
    return "-".join(uuid_parts)


def fix_title(title: str, dvd_code_tag: Tag) -> str:
    dvd_code = css.get_text(dvd_code_tag).upper()
    uncensored = "UNCENSORED" in dvd_code
    leak = "LEAK" in dvd_code
    for trash in ("-UNCENSORED", "-LEAK"):
        dvd_code = dvd_code.replace(trash, "").removesuffix("-")

    title = " ".join(word for word in title.split(" ") if dvd_code not in word.upper())
    full_dvd_code = f"{dvd_code}{(uncensored and '-UNCENSORED') or ''}{(leak and '-LEAK') or ''}"
    return f"{full_dvd_code} {title}"
