"""Kernel Video Sharing, https://www.kernel-video-sharing.com)"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures import AbsoluteHttpURL, Resolution
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, parse_url

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem


@dataclasses.dataclass(slots=True)
class KVSVideo:
    id: str
    title: str
    url: AbsoluteHttpURL
    resolution: Resolution


class Selectors:
    UNAUTHORIZED = "div.video-holder:-soup-contains('This video is a private video')"
    FLASHVARS = "script:-soup-contains('video_title:')"
    USER_NAME = "div.headline > h2"
    ALBUM_NAME = "div.headline > h1"
    ALBUM_PICTURES = "div.album-list > a"
    PICTURE = "div.photo-holder > img"
    PUBLIC_VIDEOS = "div#list_videos_public_videos_items"
    PRIVATE_VIDEOS = "div#list_videos_private_videos_items"
    FAVOURITE_VIDEOS = "div#list_videos_favourite_videos_items"
    COMMON_VIDEOS_TITLE = "div#list_videos_common_videos_list h1"
    VIDEOS = "div#list_videos_common_videos_list_items a"
    NEXT_PAGE = "li.pagination-next > a"
    ALBUM_ID = "script:-soup-contains('album_id')"
    DATE2 = "span:-soup-contains('Added:') + span"
    DATE1 = "div.info span:-soup-contains('Submitted:')"
    DATE = f"{DATE1}, {DATE2}"


_SELECTORS = Selectors()


class KernelVideoSharingCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Albums": "/albums/<album_name>",
        "Image": "/albums/<album_name>/<image_name>",
        "Search": "/search/?q=...",
        "Categories": "/categories/...",
        "Tags": "/tags/...",
        "Videos": "/videos/...",
        "Members": "/members/<member_id>",
    }

    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    _RATE_LIMIT = 3, 10

    async def fetch(self, scrape_item: ScrapeItem) -> None:
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
        soup = await self.request_soup(scrape_item.url)
        title = ""
        if (search_query := scrape_item.url.query.get("q")) or scrape_item.url.parts[1] == "search":
            search_query = search_query or scrape_item.url.parts[2]
            title = f"{search_query} [search]"
        else:
            common_title = css.select_one_get_text(soup, _SELECTORS.COMMON_VIDEOS_TITLE)
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
        soup = await self.request_soup(scrape_item.url)

        user_name: str = css.select_one_get_text(soup, _SELECTORS.USER_NAME).split("'s Profile")[0].strip()
        title = f"{user_name} [user]"
        title = self.create_title(title)
        scrape_item.setup_as_profile(title)

        if soup.select(_SELECTORS.PUBLIC_VIDEOS):
            await self.iter_videos(scrape_item, "public_videos")
        if soup.select(_SELECTORS.FAVOURITE_VIDEOS):
            await self.iter_videos(scrape_item, "favourite_videos")
        if soup.select(_SELECTORS.PRIVATE_VIDEOS):
            await self.iter_videos(scrape_item, "private_videos")

    async def iter_videos(self, scrape_item: ScrapeItem, video_category: str = "") -> None:
        url = scrape_item.url / video_category if video_category else scrape_item.url
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEOS):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        video = extract_kvs_video(self, soup)
        filename, ext = self.get_filename_and_ext(video.url.name)
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=video.resolution)
        date_str = css.select_one_get_text(soup, _SELECTORS.DATE).split(":", 1)[-1].strip()
        scrape_item.possible_datetime = self.parse_date(date_str)
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        js_text = css.select_one_get_text(soup, _SELECTORS.ALBUM_ID)
        album_id = get_text_between(js_text, "params['album_id'] =", ";").strip()
        results = await self.get_album_results(album_id)
        title = css.select_one_get_text(soup, _SELECTORS.ALBUM_NAME)
        title = self.create_title(f"{title} [album]", album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_PICTURES, results=results):
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def picture(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        url = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.PICTURE, "src"))
        filename, ext = self.get_filename_and_ext(url.name)
        await self.handle_file(url, scrape_item, filename, ext)


def extract_kvs_video(cls: Crawler, soup: BeautifulSoup) -> KVSVideo:
    if soup.select_one(_SELECTORS.UNAUTHORIZED):
        raise ScrapeError(401, "Private video")

    script = css.select_one_get_text(soup, _SELECTORS.FLASHVARS)
    video = _parse_video_vars(script)
    if not video.title:
        title = open_graph.get_title(soup) or css.page_title(soup)
        assert title
        video.title = css.sanitize_page_title(title, cls.DOMAIN)
    return video


# URL de-obfuscation code for kvs, adapted from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py


_HASH_LENGTH = 32
_match_video_url_keys = re.compile(r"^video_(?:url|alt_url\d*)$").match
_find_flashvars = re.compile(r"(\w+):\s*'([^']*)'").findall


def _parse_video_vars(video_vars: str) -> KVSVideo:
    flashvars: dict[str, str] = dict(_find_flashvars(video_vars))
    url_keys = filter(_match_video_url_keys, flashvars.keys())
    license_token = _get_license_token(flashvars["license_code"])

    def get_formats():
        for key in url_keys:
            url_str = flashvars[key]
            if "/get_file/" not in url_str:
                continue
            quality = flashvars.get(f"{key}_text")
            resolution = Resolution.highest() if quality == "HQ" else Resolution.parse(quality)
            url = _deobfuscate_url(url_str, license_token)
            yield resolution, url

    resolution, url = max(get_formats())
    return KVSVideo(flashvars["video_id"], flashvars["video_title"], url, resolution)


def _get_license_token(license_code: str) -> tuple[int, ...]:
    license_code = license_code.removeprefix("$")
    license_values = [int(char) for char in license_code]
    modlicense = license_code.replace("0", "1")
    middle = len(modlicense) // 2
    fronthalf = int(modlicense[: middle + 1])
    backhalf = int(modlicense[middle:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: middle + 1]

    return tuple(
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    )


def _deobfuscate_url(video_url_str: str, license_token: Sequence[int]) -> AbsoluteHttpURL:
    raw_url_str = video_url_str.removeprefix("function/0/")
    url = parse_url(raw_url_str)
    is_obfuscated = raw_url_str != video_url_str
    if not is_obfuscated:
        return url

    hash, tail = url.parts[3][:_HASH_LENGTH], url.parts[3][_HASH_LENGTH:]
    indices = list(range(_HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(_HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % _HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    new_parts = list(url.parts)
    new_parts[3] = "".join(hash[index] for index in indices) + tail
    return url.with_path("/".join(new_parts[1:]), keep_query=True, keep_fragment=True)
