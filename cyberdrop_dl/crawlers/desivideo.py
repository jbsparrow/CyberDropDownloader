from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    VIDEO_SRC = css.CssAttributeSelector("video.fluid-player > source", "src")
    TITLE = "strong.bread-current"
    NEXT_PAGE = "li.page-item > a:-soup-contains('›')"  # noqa: RUF001
    VIDEOS = "div.videos-list > article > a"


class DesiVideoCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/videos/<video_id>/...",
        "Search": "/search?s=<query>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://desivideo.net")
    DOMAIN: ClassVar[str] = "desivideo.net"
    FOLDER_DOMAIN: ClassVar[str] = "DesiVideo"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["search"] if query := scrape_item.url.query.get("s"):
                return await self.search(scrape_item, query)
            case ["videos", video_id, *_]:
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        soup = await self.request_soup(scrape_item.url)
        video_url = self.parse_url(Selector.VIDEO_SRC(soup))
        title = css.select_text(soup, Selector.TITLE)
        _, ext = self.get_filename_and_ext(video_url.name)

        scrape_item.uploaded_at = json_ld.upload_date(soup)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id)
        return await self.handle_file(video_url, scrape_item, video_url.name, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        title = self.create_title(query)
        scrape_item.setup_as_album(title)
        async for soup in self.web_pager(scrape_item.url):
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS):
                self.create_task(self.run(new_scrape_item, check_referer=True))
