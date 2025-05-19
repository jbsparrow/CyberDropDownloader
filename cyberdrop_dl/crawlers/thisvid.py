from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

# Selectors
UNAUTHORIZED_SELECTOR = "div.video-holder:contains('This video is a private video')"
JS_SELECTOR = "div.video-holder > script:contains('var flashvars')"
USER_NAME_SELECTOR = "div.headline > h2"
ALBUM_NAME_SELECTOR = "div.headline > h1"
ALBUM_PICTURES_SELECTOR = "div.album-list > a"
PICTURE_SELECTOR = "div.photo-holder > img"
PUBLIC_VIDEOS_SELECTOR = "div#list_videos_public_videos_items"
PRIVATE_VIDEOS_SELECTOR = "div#list_videos_private_videos_items"
FAVOURITE_VIDEOS_SELECTOR = "div#list_videos_favourite_videos_items"
COMMON_VIDEOS_TITLE_SELECTOR = "div#list_videos_common_videos_list"
VIDEOS_SELECTOR = "a.tumbpu"
ALBUM_ID_SELECTOR = "script:contains('album_id')"

# Regex
VIDEO_RESOLUTION_PATTERN = re.compile(r"video_url_text:\s*'([^']+)'")
VIDEO_INFO_PATTTERN = re.compile(
    r"video_id:\s*'(?P<video_id>[^']+)'[^}]*?"
    r"license_code:\s*'(?P<license_code>[^']+)'[^}]*?"
    r"video_url:\s*'(?P<video_url>[^']+)'[^}]*?"
)

HASH_LENGTH = 32


class Video(NamedTuple):
    id: str
    url: URL
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
        if "members" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "albums" in scrape_item.url.parts:
            if len(scrape_item.url.parts) > 3:
                return await self.picture(scrape_item)
            return await self.album(scrape_item)
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
            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if soup.select_one(UNAUTHORIZED_SELECTOR):
            raise ScrapeError(401)
        script = soup.select_one(JS_SELECTOR)
        if not script:
            raise ScrapeError(404)

        video = get_video_info(script.text)
        title: str = soup.select_one("title").text.split("- ThisVid.com")[0].strip()  # type: ignore
        filename, ext = self.get_filename_and_ext(video.url.name)
        canonical_url = self.primary_base_domain / "videos" / video.id
        scrape_item.url = canonical_url
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{video.id}] [{video.res}]{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        js_text: str = soup.select_one(ALBUM_ID_SELECTOR).text  # type: ignore
        album_id: str = get_text_between(js_text, "params['album_id'] =", ";").strip()
        results = await self.get_album_results(album_id)
        title: str = soup.select_one(ALBUM_NAME_SELECTOR).get_text(strip=True)  # type: ignore
        title = self.create_title(f"{title} [album]", album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, ALBUM_PICTURES_SELECTOR, results=results):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def picture(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        url: URL = self.parse_url(soup.select_one(PICTURE_SELECTOR)["src"])  # type: ignore
        filename, ext = self.get_filename_and_ext(url.name)
        await self.handle_file(url, scrape_item, filename, ext)


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_video_info(flashvars: str) -> Video:
    if match_id := VIDEO_INFO_PATTTERN.search(flashvars):
        video_id, license_code, url = match_id.groups()
        real_url = kvs_get_real_url(url, license_code)
        if match_res := VIDEO_RESOLUTION_PATTERN.search(flashvars):
            resolution = match_res.group(1)
        else:
            resolution = "Unknown"
        return Video(video_id, real_url, resolution)
    raise ScrapeError(404)


# URL de-obfuscation code, borrowed from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py


def kvs_get_license_token(license_code: str) -> list[int]:
    license_code = license_code.removeprefix("$")
    license_values = [int(char) for char in license_code]
    modlicense = license_code.replace("0", "1")
    middle = len(modlicense) // 2
    fronthalf = int(modlicense[: middle + 1])
    backhalf = int(modlicense[middle:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: middle + 1]

    return [
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    ]


def kvs_get_real_url(video_url: str, license_code: str) -> URL:
    if not video_url.startswith("function/0/"):
        return URL(video_url)  # not obfuscated

    parsed_url = URL(video_url.removeprefix("function/0/"))
    license_token = kvs_get_license_token(license_code)
    hash, tail = parsed_url.parts[3][:HASH_LENGTH], parsed_url.parts[3][HASH_LENGTH:]
    indices = list(range(HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    new_parts = list(parsed_url.parts)
    if not parsed_url.name:
        new_parts.pop(-1)
    new_parts[3] = "".join(hash[index] for index in indices) + tail
    return parsed_url.with_path("/".join(new_parts[1:]), keep_query=True, keep_fragment=True)
