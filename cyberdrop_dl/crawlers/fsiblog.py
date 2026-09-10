from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths, auto_task_id
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import json_ld, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    IMAGES = "a.elementor-gallery-item"
    NEXT_PAGE = "a.next"
    ARTICLE = ".elementor-post__title a"


class FSIBlogCrawler(Crawler):
    SUPPORTED_DOMAINS = "fsiblog5.com", "fsiblog5.club"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Posts": "/<category>/<title>",
        "Search": "?s=<query>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://fsiblog5.com")
    DOMAIN: ClassVar[str] = "fsiblog.com"
    FOLDER_DOMAIN: ClassVar[str] = "FSIBlog"
    OLD_DOMAINS = (
        "fsiblog.com",
        "fsiblog1.com",
        "fsiblog2.com",
        "fsiblog3.com",
        "fsiblog4.com",
        "fsiblog.club",
        "fsiblog1.club",
        "fsiblog2.club",
        "fsiblog3.club",
        "fsiblog4.club",
    )
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date:%Y-%m-%d} - {title}"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if query := scrape_item.url.query.get("s"):
            return await self.search(scrape_item, query)
        if len(scrape_item.url.parts) == 3:
            return await self.post(scrape_item)
        raise ValueError

    @property
    def separate_posts(self) -> bool:
        return True

    @error_handling_wrapper
    async def post(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        _, meta = json_ld.find(soup, "datePublished")
        name = meta["name"].rpartition("-")[0]
        scrape_item.uploaded_at = date = self.parse_iso_date(meta["datePublished"])
        title = self.create_separate_post_title(name, None, date)
        scrape_item.setup_as_album(self.create_title(title))

        if video := open_graph.get("video", soup):
            link = self.parse_url(video)
            self.create_eager_task(self.direct_file(scrape_item, link))

        for image in self.iter_urls(soup, Selector.IMAGES):
            self.create_eager_task(self.direct_file(scrape_item, image))

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        title = self.create_title(query)
        scrape_item.setup_as_album(title)
        async for soup in self.web_pager(scrape_item.url):
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.ARTICLE):
                self.create_task(self._post_task(new_scrape_item))

    _post_task = auto_task_id(post)
