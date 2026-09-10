from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, final

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, URLConfig
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    VIDEO_PLAYER = "video.video-js > source"
    TITLE = "h1.title-right"
    NEXT_PAGE = "div#pagination > a:-soup-contains('»')"
    VIDEOS_THUMBS = "div.contents div.content a"


@HTTPConfig(rate_limit=(3, 10))
@URLConfig(trim=False)
class LuxureTVCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/videos/<name>-<id>.html",
        "Search": "/searchgate/videos/<search>/...",
    }
    DOMAIN: ClassVar[str] = "luxuretv"
    FOLDER_DOMAIN: ClassVar[str] = "LuxureTV"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://luxuretv.com")
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["searchgate", "videos", query, *_]:
                return await self.search(scrape_item, query)
            case ["videos", slug, *_]:
                video_id = slug.split("-")[-1].split(".")[0]
                return await self.video(scrape_item, video_id)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        title = query.replace("-", " ").capitalize()
        title = self.create_title(f"{title} [search]")
        scrape_item.setup_as_album(title)
        url = scrape_item.url
        if url.name and not url.name.endswith(".html"):
            url /= ""

        async for soup in self.web_pager(url, impersonate=True):
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS_THUMBS):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        soup = await self.request_soup(scrape_item.url, impersonate=True)

        scrape_item.uploaded_at = json_ld.upload_date(soup)
        video_player = css.select(soup, Selector.VIDEO_PLAYER)
        title = css.select_text(soup, Selector.TITLE)
        link = self.parse_url(css.attr(video_player, "src"))
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id)

        return await self.handle_file(
            scrape_item.url,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename,
            debrid_link=link,
        )
