from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_og_properties

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


M3U8_SERVER = AbsoluteHttpURL("https://surrit.com/")
PRIMARY_URL = AbsoluteHttpURL("https://missav.ws")
DATE_SELECTOR = "div > span:contains('Release date:') + time"
DVD_CODE_SELECTOR = "div > span:contains('Code:') + span"


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

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.DOMAIN, scrape_item.url)

        title = get_og_properties(soup).title.strip()
        date_tag = soup.select_one(DATE_SELECTOR)
        dvd_code_tag = soup.select_one(DVD_CODE_SELECTOR)

        date_str: str = css.get_attr(date_tag, "datetime") if date_tag else ""
        dvd_code = css.get_text(dvd_code_tag).upper() if dvd_code_tag else None

        if dvd_code:
            for trash in (dvd_code.lower(), dvd_code.upper()):
                title = title.replace(trash, "").strip()
            title = f"{dvd_code} {title}"

        scrape_item.possible_datetime = self.parse_date(date_str)
        uuid = get_uuid(soup)
        m3u8_playlist_url = M3U8_SERVER / uuid / "playlist.m3u8"
        m3u8_media, rendition_group = await self.get_m3u8_playlist(m3u8_playlist_url)
        title = Path(title).as_posix().replace("/", "-")  # remove OS separators
        filename, ext = self.get_filename_and_ext(f"{title} [{rendition_group.resolution.name}].mp4")
        await self.handle_file(m3u8_playlist_url, scrape_item, filename, ext, m3u8_media=m3u8_media)


def get_uuid(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, "script:contains('m3u8|')")
    uuid_joined_parts = js_text.split("m3u8|", 1)[-1].split("|com|surrit", 1)[0]
    uuid_parts = reversed(uuid_joined_parts.split("|"))
    return "-".join(uuid_parts)
