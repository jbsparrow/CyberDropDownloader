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


# Selectors
JS_SELECTOR = "div.video-holder script:contains('var flashvars')"
NEXT_PAGE_SELECTOR = "div#list_videos_videos_pagination li.next"
USER_NAME_SELECTOR = "div.user-name"
VIDEOS_SELECTOR = "div.video-list a.thumb"

# Regex
VIDEO_INFO_FIELDS_PATTERN = re.compile(r"(\w+):\s*'([^']*)'")


class PorntrexCrawler(Crawler):
    primary_base_domain = URL("https://www.porntrex.com")
    next_page_selector = NEXT_PAGE_SELECTOR

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
        # The ending / is necessary or we get a 404 error
        url: URL = scrape_item.url / "videos/"
        title_created: bool = False
        async for soup in self.web_pager(url):
            if not title_created:
                user_name: str = soup.select_one(USER_NAME_SELECTOR).get_text(strip=True)
                title = f"{user_name} [user]"
                title = self.create_title(title)
                scrape_item.setup_as_profile(title)
                title_created = True
            scrape_item.url = url
            # Todo Write the ajax paginator
            # last_page: str = soup.select("div.pagination-holder li.page")[-1].get_text(strip=True)
            # url = URL(
            #     "https://www.porntrex.com/members/5685841/videos/?mode=async&function=get_block&block_id=list_videos_uploaded_videos&is_private=0,1&sort_by=&from_uploaded_videos=664"
            # )
            # async with self.request_limiter:
            #     temp_soup: BeautifulSoup = await self.client.get_soup(self.domain, url)
            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

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
