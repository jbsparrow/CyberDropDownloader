from __future__ import annotations

import calendar
import datetime
import json
import re
from typing import TYPE_CHECKING, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


PROFILE_VIDEOS_SELECTOR = "div.media-item__inner a[data-video-preview]"
MODEL_VIDEO_SELECTOR = "a data-video-preview"
USER_NAME_SELECTOR = "h1.username"
PLAYLIST_VIDEOS_SELECTOR = "a.playlist-video-item__thumbnail"
VIDEO_OBJECT_SCRIPT_SELECTOR = "script:contains('uploadDate')"
JS_SELECTOR = "script:contains('var player = new VideoPlayer')"
LOGIN_REQUIRED_SELECTOR = "div.loginLinks:contains('To watch this video please')"
RESOLUTIONS = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
INCLUDE_VIDEO_ID_IN_FILENAME = True


class Format(NamedTuple):
    resolution: str
    link_str: str


class AShemaleTubeCrawler(Crawler):
    primary_base_domain = URL("https://www.ashemaletube.com")
    next_page_selector = "a.rightKey"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "ashemaletube", "aShemaleTube")
        self.request_limiter = AsyncLimiter(3, 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("creators", "profiles", "pornstars", "model")):
            return await self.model(scrape_item)
        elif "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        elif "playlists" in scrape_item.url.parts:
            return await self.playlist(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        title = ""
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            if not title:
                playlist_name = soup.select_one("h1").get_text(strip=True)  # type: ignore
                title = self.create_title(f"{playlist_name} [playlist]")
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, PLAYLIST_VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)
        title = ""
        async for soup in self.web_pager(scrape_item.url, cffi=True):
            if not title:
                model_name = soup.select_one(USER_NAME_SELECTOR).get_text(strip=True)  # type: ignore
                title = self.create_title(f"{title} [model]")
                scrape_item.setup_as_profile(model_name)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, PROFILE_VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id: str = scrape_item.url.parts[2]
        canonical_url = self.primary_base_domain / "videos" / video_id
        if await self.check_complete_from_referer(scrape_item.url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup_cffi(self.domain, scrape_item.url)

        if soup.select_one(LOGIN_REQUIRED_SELECTOR):
            raise ScrapeError(401)
        player = soup.select_one(JS_SELECTOR)
        if not player:
            raise ScrapeError(422)
        is_hls, best_format = parse_player_info(player.text)
        if is_hls:
            raise ScrapeError(422)

        if video_object := soup.select_one(VIDEO_OBJECT_SCRIPT_SELECTOR):
            json_data = json.loads(video_object.text.strip())
            if "uploadDate" in json_data:
                scrape_item.possible_datetime = parse_datetime(json_data["uploadDate"])

        title: str = soup.select_one("title").text.split("- aShemaletube.com")[0].strip()  # type: ignore
        link = self.parse_url(best_format.link_str)

        scrape_item.url = canonical_url
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=".mp4")
        include_id = f"[{video_id}]" if INCLUDE_VIDEO_ID_IN_FILENAME else ""
        custom_filename, _ = self.get_filename_and_ext(f"{title} {include_id}[{best_format.resolution}]{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
        )


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_best_quality(info_dict: dict) -> Format:
    """Returns best available format"""
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


def parse_player_info(script_text: str) -> tuple[bool, Format]:
    if match := re.search(r"hls:\s+(true|false)", script_text):
        is_hls = match.group(1) == "true"
        urls_info = "[{" + get_text_between(script_text, "[{", "}],") + "}]"
        format: Format = get_best_quality(json.loads(urls_info))
        return is_hls, format
    raise ScrapeError(404)


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    dt = datetime.datetime.fromisoformat(date)
    return calendar.timegm(dt.timetuple())
