from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, kvs
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://thisvid.com")


class Selectors:
    UNAUTHORIZED = "div.video-holder:contains('This video is a private video')"
    FLASHVARS = "div.video-holder > script:contains('var flashvars')"
    USER_NAME = "div.headline > h2"
    ALBUM_NAME = "div.headline > h1"
    ALBUM_PICTURES = "div.album-list > a"
    PICTURE = "div.photo-holder > img"
    PUBLIC_VIDEOS = "div#list_videos_public_videos_items"
    PRIVATE_VIDEOS = "div#list_videos_private_videos_items"
    FAVOURITE_VIDEOS = "div#list_videos_favourite_videos_items"
    COMMON_VIDEOS_TITLE = "div#list_videos_common_videos_list"
    VIDEOS = "a.tumbpu"
    ALBUM_ID = "script:contains('album_id')"
    DATE_ADDED = ".tools-left > li:nth-child(4) > span:nth-child(2)"


_SELECTORS = Selectors()


class ThisVidCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Albums": "/albums/<album_name>",
        "Image": "/albums/<album_name>/<image_name>",
        "Search": "/search/?q=...",
        "Categories": "/categories/...",
        "Tags": "/tags/...",
        "Videos": "/videos/...",
        "Members": "/members/<member_id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "li.pagination-next > a"
    DOMAIN: ClassVar[str] = "thisvid"
    FOLDER_DOMAIN: ClassVar[str] = "ThisVid"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 10)

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
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        title = ""
        if search_query := scrape_item.url.query.get("q"):
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
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

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
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if soup.select_one(_SELECTORS.UNAUTHORIZED):
            raise ScrapeError(401)
        script = soup.select_one(_SELECTORS.FLASHVARS)
        if not script:
            raise ScrapeError(404)

        video = kvs.get_video_info(script.text)
        if not video:
            raise ScrapeError(404)
        title: str = css.select_one_get_text(soup, "title").split("- ThisVid.com")[0].strip()
        filename, ext = self.get_filename_and_ext(video.url.name)
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{video.id}] [{video.res}]{ext}")
        scrape_item.possible_datetime = self.parse_date(css.select_one_get_text(soup, _SELECTORS.DATE_ADDED))
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        js_text: str = css.select_one_get_text(soup, _SELECTORS.ALBUM_ID)
        album_id: str = get_text_between(js_text, "params['album_id'] =", ";").strip()
        results = await self.get_album_results(album_id)
        title: str = css.select_one_get_text(soup, _SELECTORS.ALBUM_NAME)
        title = self.create_title(f"{title} [album]", album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_PICTURES, results=results):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def picture(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        url = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.PICTURE, "src"))
        filename, ext = self.get_filename_and_ext(url.name)
        await self.handle_file(url, scrape_item, filename, ext)
