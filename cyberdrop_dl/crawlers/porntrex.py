from __future__ import annotations

import itertools
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


class Selectors:
    JS_SELECTOR = "div.video-holder script:contains('var flashvars')"
    NEXT_PAGE_SELECTOR = "div#list_videos_videos_pagination li.next"
    USER_NAME_SELECTOR = "div.user-name"
    VIDEOS_SELECTOR = "div.video-list a.thumb"
    LAST_PAGE_SELECTOR = "div.pagination-holder li.page"
    TITLE_SELECTOR = "div.headline > h1"
    MODEL_NAME_SELECTOR = "div.name > h1"
    ALBUM_TITLE = "div.album-info p.title-video"
    IMAGES_SELECTOR = "a[rel=images].item"


VIDEO_INFO_FIELDS_PATTERN = re.compile(r"(\w+):\s*'([^']*)'")
COLLECTION_PARTS = "tags", "categories", "models", "playlists", "search"
TITLE_TRASH = "Free HD", "Most Relevant", "New", "Videos", "Porn", "for:", "New Videos", "Tagged with"
_SELECTORS = Selectors()


class PorntrexCrawler(Crawler):
    primary_base_domain = URL("https://www.porntrex.com")
    next_page_selector = _SELECTORS.NEXT_PAGE_SELECTOR

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "porntrex", "Porntrex")
        self.request_limiter = AsyncLimiter(3, 10)

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if scrape_item.url.name:  # The ending slash is necessary or we get a 404 error
            scrape_item.url = scrape_item.url / ""

        if len(scrape_item.url.parts) > 3:
            if "members" in scrape_item.url.parts:
                return await self.profile(scrape_item)
            if "albums" in scrape_item.url.parts:
                return await self.album(scrape_item)
            elif "video" in scrape_item.url.parts:
                return await self.video(scrape_item)
            if any(p in scrape_item.url.parts for p in COLLECTION_PARTS):
                return await self.collection(scrape_item)

        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_id = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "This album is a private album" in soup.text:
            raise ScrapeError(401, "Private album")

        title = soup.select_one(_SELECTORS.ALBUM_TITLE).text  # type: ignore
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title)

        for _, link in self.iter_tags(soup, _SELECTORS.IMAGES_SELECTOR):
            filename, ext = self.get_filename_and_ext(link.name)
            canonical_url = self.primary_base_domain / "albums" / album_id / filename
            await self.handle_file(canonical_url, scrape_item, filename, ext, debrid_link=link)
            scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id = scrape_item.url.parts[2]
        canonical_url = self.primary_base_domain / "video" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        video = get_video_info(soup)
        filename, ext = self.get_filename_and_ext(video.url.name)
        scrape_item.url = canonical_url
        custom_filename, _ = self.get_filename_and_ext(f"{video.title} [{video.id}] [{video.res}]{ext}")
        await self.handle_file(
            canonical_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "models" in scrape_item.url.parts:
            title: str = soup.select_one(_SELECTORS.MODEL_NAME_SELECTOR).get_text(strip=True).title()  # type: ignore
        else:
            title = soup.select_one(_SELECTORS.TITLE_SELECTOR).get_text(strip=True)  # type: ignore

        for trash in TITLE_TRASH:
            title = title.replace(trash, "").strip()

        if "categories" in scrape_item.url.parts:
            collection_type = "category"
        else:
            collection_type = next(p for p in COLLECTION_PARTS if p in scrape_item.url.parts).removesuffix("s")

        title, *_ = title.split(",Page")
        title = self.create_title(f"{title} [{collection_type}]")
        scrape_item.setup_as_album(title)
        last_page_tag = soup.select(_SELECTORS.LAST_PAGE_SELECTOR)
        last_page: int = int(last_page_tag[-1].get_text(strip=True)) if last_page_tag else 1

        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEOS_SELECTOR):
            self.manager.task_group.create_task(self.run(new_scrape_item))

        await self.proccess_additional_pages(scrape_item, last_page)

        if "models" in scrape_item.url.parts:
            await self.proccess_additional_pages(scrape_item, last_page, block_id="list_albums_common_albums_list")

    async def proccess_additional_pages(self, scrape_item: ScrapeItem, last_page: int, **kwargs: str) -> None:
        block_id: str = "list_videos_common_videos_list_norm"
        search_query: str = ""
        sort_by: str = scrape_item.url.parts[4] if len(scrape_item.url.parts) > 4 else ""
        sort_by = sort_by or scrape_item.url.query.get("sort_by") or "post_date"
        if "search" in scrape_item.url.parts:
            search_query = scrape_item.url.parts[3]  # type: ignore
            block_id = "list_videos_videos"

        elif "playlists" in scrape_item.url.parts:
            block_id = "playlist_view_playlist_view_dev"
            sort_by = "added2fav_date"

        page_url = scrape_item.url.with_path("/".join(scrape_item.url.parts[1:3])) / ""
        page_url = page_url.with_query(
            mode="async", function="get_block", block_id=block_id, is_private=0, q=search_query, sort_by=sort_by
        )
        if kwargs:
            page_url.update_query(kwargs)

        if "videos" not in page_url.query["block_id"]:
            from_param_name = "from1"
        else:
            from_param_name: str = "from"

        for page in itertools.count(2):
            if page > last_page:
                break
            page_url = page_url.update_query({from_param_name: page})
            async with self.request_limiter:
                soup = await self.client.get_soup(self.domain, page_url)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_video_info(soup: BeautifulSoup) -> Video:
    script = soup.select_one(_SELECTORS.JS_SELECTOR)
    if not script:
        raise ScrapeError(404)

    flashvars = get_text_between(script.text, "var flashvars =", "var player_obj =")

    def extract_resolution(res_text):
        match = re.search(r"(\d+)", res_text)
        return int(match.group(1)) if match else 0

    video_info: dict[str, str] = dict(VIDEO_INFO_FIELDS_PATTERN.findall(flashvars))
    if video_info:
        resolutions: list[tuple[str, str]] = []
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

        if not resolutions:
            resolutions.append((video_info["video_url"], "Unknown"))

        best = max(resolutions, key=lambda x: extract_resolution(x[0]))
        return Video(video_info["video_id"], video_info["video_title"], URL(best[1].strip("/")), best[0].split()[0])
    raise ScrapeError(404)
