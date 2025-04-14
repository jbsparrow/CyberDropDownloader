from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


class Video(NamedTuple):
    id: str
    title: str
    url: URL
    res: str


JS_SELECTOR = "div.video-holder script:contains('var flashvars')"
VIDEO_INFO_FIELDS_PATTERN = re.compile(r"(\w+):\s*'([^']*)'")


class PorntrexCrawler(Crawler):
    primary_base_domain = URL("https://www.porntrex.com")
    next_page_selector = "div#list_videos_videos_pagination li.next"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "porntrex", "Porntrex")
        self.request_limiter = AsyncLimiter(3, 10)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "search" in scrape_item.url.parts:
            return await self.search(scrape_item)
        elif "members" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        elif "video" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        pass

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        pass

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        script = soup.select_one(JS_SELECTOR)
        if not script:
            raise ScrapeError(404)

        video = get_video_info(get_text_between(script.text, "var flashvars =", "var player_obj ="))
        filename, ext = self.get_filename_and_ext(video.url.name)
        canonical_url = self.primary_base_domain / "video" / video.id
        scrape_item.url = canonical_url
        custom_filename, _ = self.get_filename_and_ext(f"{video.title} [{video.id}] [{video.res}]{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_video_info(flashvars: str) -> Video:
    def extract_resolution(res_text):
        match = re.search(r"(\d+)", res_text)
        return int(match.group(1)) if match else 0

    video_info = dict(VIDEO_INFO_FIELDS_PATTERN.findall(flashvars))
    if video_info:
        resolutions = []
        if "video_url" in video_info and "video_url_text" in video_info:
            resolutions.append((video_info["video_url_text"], video_info["video_url"]))

        for key in video_info:
            if (
                key.startswith("video_alt_url")
                and not key.endswith("_hd")
                and not key.endswith("_4k")
                and not key.endswith("_text")
            ):
                text_key = f"{key}_text"
                if text_key in video_info:
                    resolutions.append((video_info[text_key], video_info[key]))

        best = max(resolutions, key=lambda x: extract_resolution(x[0]))
        return Video(video_info["video_id"], video_info["video_title"], URL(best[1].strip("/")), best[0].split()[0])
    raise ScrapeError(404)
