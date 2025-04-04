from __future__ import annotations

import calendar
import datetime
import json
import re
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PRIMARY_BASE_DOMAIN = URL("https://www.ashemaletube.com")
VIDEO_SELECTOR = "video > source"
PROFILE_SELECTOR = "div#ajax-profile-content div.media-item__inner"
MODEL_VIDEO_SELECTOR = "a data-video-preview"
DATETIME_SELECTOR = "div.views-count-add"
JS_SELECTOR = "script:contains('var player = new VideoPlayer')"
RESOLUTIONS = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
INCLUDE_VIDEO_ID_IN_FILENAME = True


class Format(NamedTuple):
    resolution: str
    link_str: str


class AShemaleTubeCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "ashemaletube", "aShemaletube")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "model" in scrape_item.url.parts:
            return await self.model(scrape_item)
        elif "playlist" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None: ...

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        for item in soup.select(PROFILE_SELECTOR):
            if model_video := item.select_one("a"):
                link: URL = create_canonical_video_url(model_video.get("href"))
                new_scrape_item = scrape_item.create_child(link, new_title_part="Model")
                await self.video(new_scrape_item)
                scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        if player := soup.select_one(JS_SELECTOR):
            info: dict[str, str | dict] = parse_player_info(player.text)
            if info is None:
                raise ScrapeError(404, origin=scrape_item)
            if info["hls"]:
                raise ScrapeError(422, origin=scrape_item)

            if date_added := soup.select_one(DATETIME_SELECTOR):
                scrape_item.possible_datetime = parse_datetime(date_added.get_text(strip=True))

            video_id: str = scrape_item.url.parts[2]
            title: str = soup.select_one("title").text.split("- aShemaletube.com")[0].strip()
            filename, ext = self.get_filename_and_ext(info["url"], assume_ext=".mp4")
            include_id = f"[{video_id}]" if INCLUDE_VIDEO_ID_IN_FILENAME else ""
            custom_filename = f"{title} {include_id}[{info['res']}]{ext}"
            await self.handle_file(URL(info["url"]), scrape_item, filename, ext, custom_filename=custom_filename)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def create_canonical_video_url(href: str) -> URL:
    return URL(f"{PRIMARY_BASE_DOMAIN}{href}")


def get_best_quality(info_dict: dict) -> Format:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""

    active_url: str = ""
    active_res: str = ""
    for res in RESOLUTIONS:
        for item in info_dict:
            if item["active"] == "true":
                active_url = item["src"]
                active_res = item["desc"]
            if res == item["desc"]:
                return Format(res, item["src"])

    return Format(active_res, active_url)


def parse_player_info(script_text: str) -> dict[str, str | dict] | None:
    info: dict[str, str | dict] = {}
    if match := re.search(r"hls:\s+(true|false)", script_text):
        info["hls"] = match.group(1) == "true"
    if "hls" not in info:
        return None
    urls_info = script_text[script_text.find("[{") : script_text.find("}],") + 2]
    format: Format = get_best_quality(json.loads(urls_info))
    info["url"] = format.link_str
    info["res"] = format.resolution
    return info


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "Added %Y-%m-%d")
    return calendar.timegm(parsed_date.timetuple())


def is_playlist(url: URL) -> bool:
    return False
