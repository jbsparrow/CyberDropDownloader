from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.m3u8 import M3U8
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


M3U8_SERVER = URL("https://surrit.com/")
TITLE_SELECTOR = "meta [property='og:title']"
DATE_SELECTOR = "div > span:contains('Release date:') + time"
DVD_CODE_SELECTOR = "div > span:contains('Code:') + span"
M3U8_SELECTOR = "script:contains('m3u8|')"


class MissAVCrawler(Crawler):
    primary_base_domain = URL("https://missav.ws")

    def __init__(self, manager: Manager, _=None) -> None:
        super().__init__(manager, "missav", "MissAV")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        canonical_url = self.primary_base_domain / "en" / scrape_item.url.name
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, canonical_url)

        scrape_item.url = canonical_url
        title = clean_title = soup.select_one(TITLE_SELECTOR)["content"].strip()  # type: ignore
        date_tag = soup.select_one(DATE_SELECTOR)

        # Some videos may not have it
        date_str: str = date_tag.get("datetime") if date_tag else ""  # type: ignore
        if date_str:
            scrape_item.possible_datetime = self.parse_date(date_str)

        # Some videos may not have it
        dvd_code = tag.text.strip() if (tag := soup.select_one(DVD_CODE_SELECTOR)) else None
        if dvd_code:
            for value in (dvd_code.lower(), dvd_code.upper()):
                clean_title = clean_title.replace(value, "").strip()
            title = f"{dvd_code} {clean_title}"

        uuid = get_uuid(soup)
        m3u8_playlist_url = M3U8_SERVER / uuid / "playlist.m3u8"

        async with self.request_limiter:
            m3u8_playlist_content: str = await self.client.get_text(self.domain, m3u8_playlist_url)

        best_format = M3U8(m3u8_playlist_content).best_format
        m3u8_video_url = M3U8_SERVER / uuid / best_format.name

        async with self.request_limiter:
            m3u8_video_content: str = await self.client.get_text(self.domain, m3u8_video_url)

        m3u8_video = M3U8(m3u8_video_content, m3u8_video_url.parent)
        filename = f"{title} [{best_format.height}].mp4"
        filename, ext = self.get_filename_and_ext(filename)
        await self.handle_file(m3u8_playlist_url, scrape_item, filename, ext, m3u8=m3u8_video)


def get_uuid(soup: BeautifulSoup) -> str:
    js_text = script.text if (script := soup.select_one(M3U8_SELECTOR)) else None
    if not js_text:
        raise ScrapeError(422)

    uuid_reversed_parts = get_text_between(js_text, "m3u8|", "|com|surrit")
    uuid_parts = reversed(uuid_reversed_parts.split("|"))
    return "-".join(uuid_parts)
