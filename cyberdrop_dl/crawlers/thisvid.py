from __future__ import annotations

import re
import urllib
from typing import TYPE_CHECKING, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
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
VIDEOS_SELECTOR = "a.tumbpu"
VIDEO_RESOLUTION_PATTERN = re.compile(r"video_url_text:\s*'([^']+)'")
VIDEO_INFO_PATTTERN = re.compile(
    r"video_id:\s*'(?P<video_id>[^']+)'[^}]*?"
    r"license_code:\s*'(?P<license_code>[^']+)'[^}]*?"
    r"video_url:\s*'(?P<video_url>[^']+)'[^}]*?"
)


class Video(NamedTuple):
    id: str
    url: str
    res: str


class ThisVidCrawler(Crawler):
    primary_base_domain = URL("https://thisvid.com")
    next_page_selector = "li.pagination-next > a"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "thisvid", "ThisVid")
        self.request_limiter = AsyncLimiter(3, 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if any(p in scrape_item.url.parts for p in ("categories", "tags")) or scrape_item.url.query.get("q"):
            return await self.search(scrape_item)
        elif "members" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        elif "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        title = ""
        if search_query := scrape_item.url.query.get("q"):
            title = f"{search_query} [search]"
        else:
            category_title = soup.select_one(COMMON_VIDEOS_TITLE_SELECTOR)
            common_title: str = category_title.get_text(strip=True)  # type: ignore
            if common_title.startswith("New Videos Tagged"):
                common_title = common_title.split("Showing")[0].split("Tagged with")[1].strip()
                title = f"{common_title} [tag]"
            else:
                common_title = common_title.split("New Videos")[0].strip()
                title = f"{common_title} [category]"

        title = self.create_title(title)
        scrape_item.setup_as_album(title)
        await self.iter_videos(scrape_item)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        user_name: str = soup.select_one(USER_NAME_SELECTOR).get_text().split("'s Profile")[0].strip()  # type: ignore
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
            for _, new_scrape_item in self.iter_children(scrape_item, soup.select(VIDEOS_SELECTOR)):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if soup.select_one(UNAUTHORIZED_SELECTOR):
            raise ScrapeError(401)
        script = soup.select_one(JS_SELECTOR)
        if script is None:
            raise ScrapeError(404)

        video = get_video_info(script.text)
        link = self.parse_url(video.url)
        title: str = soup.select_one("title").text.split("- ThisVid.com")[0].strip()  # type: ignore
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename, _ = get_filename_and_ext(f"{title} [{video.id}] [{video.res}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_video_info(flashvars: str) -> Video:
    if (match_id := VIDEO_INFO_PATTTERN.search(flashvars)) and (
        match_res := VIDEO_RESOLUTION_PATTERN.search(flashvars)
    ):
        video_id = match_id.group("video_id")
        video_url = kvs_get_real_url(match_id.group("video_url"), match_id.group("license_code"))
        video_res = match_res.group(1)
        return Video(video_id, video_url, video_res)
    raise ScrapeError(404)


# URL de-obfuscation code, borrowed from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py
def kvs_get_license_token(license_code: str):
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


def kvs_get_real_url(video_url: str, license_code: str) -> str:
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
