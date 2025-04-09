from __future__ import annotations

import re
import urllib
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


UNAUTHORIZED_SELECTOR = "div.video-holder:contains('This video is a private video')"
JS_SELECTOR = "div.video-holder > script:contains('var flashvars')"
USER_NAME_SELECTOR = "div.headline > h2"
PUBLIC_VIDEOS_SELECTOR = "div#list_videos_public_videos_items"
PRIVATE_VIDEOS_SELECTOR = "div#list_videos_private_videos_items"
FAVOURITE_VIDEOS_SELECTOR = "div#list_videos_favourite_videos_items"
COMMON_VIDEOS_TITLE_SELECTOR = "div#list_videos_common_videos_list"
NEXT_PAGE_SELECTOR = "li.pagination-next > a"
VIDEOS_SELECTOR = "a.tumbpu"
VIDEO_RESOLUTION_PATTERN = re.compile(r"video_url_text:\s*'([^']+)'")
VIDEO_INFO_PATTTERN = re.compile(
    r"video_id:\s*'(?P<video_id>[^']+)'[^}]*?"
    r"license_code:\s*'(?P<license_code>[^']+)'[^}]*?"
    r"video_url:\s*'(?P<video_url>[^']+)'[^}]*?",
)


class ThisVidCrawler(Crawler):
    primary_base_domain = URL("https://thisvid.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "thisvid", "ThisVid")
        self.request_limiter = AsyncLimiter(3, 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("categories", "tags")) or scrape_item.url.query_string:
            return await self.search(scrape_item)
        elif "members" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        elif "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        title = ""
        if not scrape_item.url.query_string:
            category_title = soup.select_one(COMMON_VIDEOS_TITLE_SELECTOR)
            common_title = category_title.get_text(strip=True)
            if common_title.startswith("New Videos Tagged"):
                common_title = common_title.split("Showing")[0].split("Tagged with")[1].strip()
                title = f"{common_title} [tag]"
            else:
                common_title = category_title.get_text(strip=True).split("New Videos")[0].strip()
                title = f"{common_title} [category]"
        else:
            query_string: str = scrape_item.url.query_string.split("=")[1]
            title = f"{query_string} [search]"
        title = self.create_title(title)
        scrape_item.setup_as_album(title)
        await self.iter_videos(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        user_name: str = soup.select_one(USER_NAME_SELECTOR).get_text().split("'s Profile")[0].strip()
        title = f"{user_name} [user]"
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        if soup.select(PUBLIC_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "public_videos")
        if soup.select(FAVOURITE_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "favourite_videos")
        if soup.select(PRIVATE_VIDEOS_SELECTOR):
            await self.iter_videos(scrape_item, "private_videos")

    async def iter_videos(self, scrape_item: ScrapeItem, video_category: str = "") -> None:
        url: URL = scrape_item.url / video_category if video_category else scrape_item.url
        async for soup in self.web_pager(url):
            if videos := soup.select(VIDEOS_SELECTOR):
                for video in videos:
                    link: URL = URL(video.get("href"))
                    new_scrape_item = scrape_item.create_child(link, new_title_part=video_category)
                    self.manager.task_group.create_task(self.run(new_scrape_item))
                    scrape_item.add_children()

    async def web_pager(self, category_url: URL) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url: URL = category_url
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
            next_page = soup.select_one(NEXT_PAGE_SELECTOR)
            yield soup
            page_url_str: str | None = next_page.get("href") if next_page else None  # type: ignore
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, self.primary_base_domain)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        if soup.select_one(UNAUTHORIZED_SELECTOR):
            raise ScrapeError(401, origin=scrape_item)
        script = soup.select_one(JS_SELECTOR)
        if script is None:
            raise ScrapeError(404, origin=scrape_item)
        video_info = get_video_info(script.text)
        if "video_url" not in video_info:
            raise ScrapeError(404, origin=scrape_item)
        title: str = soup.select_one("title").text.split("- ThisVid.com")[0].strip()
        filename, ext = get_filename_and_ext(video_info["video_url"])
        video_url: URL = URL(video_info["video_url"])
        custom_filename, _ = get_filename_and_ext(
            f"{title} [{video_info['video_id']}] [{video_info['video_url_text']}].{ext}"
        )
        await self.handle_file(video_url, scrape_item, filename, ext, custom_filename=custom_filename)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_video_info(flashvars: str) -> dict:
    info = {"video_url_text": "Unknown"}
    if m := VIDEO_INFO_PATTTERN.search(flashvars):
        info["video_id"] = m.group("video_id")
        info["video_url"] = kvs_get_real_url(m.group("video_url"), m.group("license_code"))
    if m := VIDEO_RESOLUTION_PATTERN.search(flashvars):
        info["video_url_text"] = m.group(1)
    return info


# URL de-obfuscation code, borrowed from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py
def kvs_get_license_token(license_code):
    license_code = license_code.replace("$", "")
    license_values = [int(char) for char in license_code]

    modlicense = license_code.replace("0", "1")
    center = len(modlicense) // 2
    fronthalf = int(modlicense[: center + 1])
    backhalf = int(modlicense[center:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: center + 1]

    return [
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    ]


def kvs_get_real_url(video_url, license_code):
    if not video_url.startswith("function/0/"):
        return video_url  # not obfuscated

    parsed = urllib.parse.urlparse(video_url[len("function/0/") :])
    license_token = kvs_get_license_token(license_code)
    urlparts = parsed.path.split("/")

    HASH_LENGTH = 32
    hash_ = urlparts[3][:HASH_LENGTH]
    indices = list(range(HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    urlparts[3] = "".join(hash_[index] for index in indices) + urlparts[3][HASH_LENGTH:]
    return urllib.parse.urlunparse(parsed._replace(path="/".join(urlparts)))
