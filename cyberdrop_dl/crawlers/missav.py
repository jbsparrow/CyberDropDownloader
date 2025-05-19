from __future__ import annotations

import calendar
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


M3U8_SERVER = URL("https://surrit.com/")
TITLE_SELECTOR = "meta [property='og:title']"

DATE_SELECTOR = "div > span:contains('Release date:') + time"
DVD_CODE_SELECTOR = "div > span:contains('Code:') + span"


class Format(NamedTuple):
    height: int
    width: int


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
        scrape_item.url = canonical_url
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)

        title = clean_title = soup.select_one(TITLE_SELECTOR)["content"].strip()  # type: ignore
        date_tag = soup.select_one(DATE_SELECTOR)
        dvd_code_tag = soup.select_one(DVD_CODE_SELECTOR)

        date_str: str = date_tag.get("datetime") if date_tag else ""  # type: ignore
        dvd_code = dvd_code_tag.text.strip().upper() if dvd_code_tag else None

        if dvd_code:
            clean_title = clean_title.replace(dvd_code.lower(), "").replace(dvd_code.upper(), "").strip()
            title = f"{dvd_code} {clean_title}"

        if date_str:
            date = parse_datetime(date_str)
            scrape_item.possible_datetime = date

        uuid = get_uuid(soup)
        del soup
        m3u8_playlist_url = M3U8_SERVER / uuid / "playlist.m3u8"

        async with self.request_limiter:
            m3u8_playlist_content: str = await self.client.get_text(self.domain, m3u8_playlist_url)

        playlist_name, resolution = get_best_resolution(m3u8_playlist_content)
        m3u8_video_url = M3U8_SERVER / uuid / playlist_name
        video_part_base_url = m3u8_video_url.parent

        async with self.request_limiter:
            m3u8_video_content: str = await self.client.get_text(self.domain, m3u8_video_url)

        title = Path(title).as_posix().replace("/", "-")  # remove OS separators
        filename = f"{title} [{resolution}].mp4"
        filename, ext = self.get_filename_and_ext(filename)

        await self.handle_file(
            m3u8_playlist_url,
            scrape_item,
            filename,
            ext,
            m3u8_content=m3u8_video_content,
            debrid_link=video_part_base_url,
        )


def get_best_resolution(m3u8_playlist_content: str) -> tuple[str, str]:
    resolutions = get_available_formats(m3u8_playlist_content)
    best_resolution = max(resolutions)
    name = get_playlist_name(m3u8_playlist_content, best_resolution)
    return name, f"{best_resolution.height}p"


def get_available_formats(m3u8_playlist_content: str) -> Generator[Format]:
    for line in m3u8_playlist_content.splitlines():
        if "RESOLUTION=" not in line:
            continue
        dimentions = line.split("RESOLUTION=")[-1].strip().split("x")
        yield Format(*map(int, reversed(dimentions)))


def get_playlist_name(m3u8_playlist_content: str, res: Format) -> str:
    format_str = f"{res.width}x{res.height}"
    get_next = False
    for line in m3u8_playlist_content.splitlines():
        if get_next:
            return line.strip()
        if f"RESOLUTION={format_str}" in line:
            get_next = True

    raise ScrapeError(422)


def get_uuid(soup: BeautifulSoup) -> str:
    info_js_script = soup.select_one("script:contains('m3u8|')")
    js_text = info_js_script.text if info_js_script else None
    if not js_text:
        raise ScrapeError(422)

    uuid_joined_parts = js_text.split("m3u8|", 1)[-1].split("|com|surrit", 1)[0]
    uuid_parts = reversed(uuid_joined_parts.split("|"))
    return "-".join(uuid_parts)


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.fromisoformat(date)
    return calendar.timegm(parsed_date.timetuple())
