from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL, ScrapeItem, ScrapeItemType
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper


class Selector:
    CHAPTER = ".wp-manga-chapter a"
    IMAGE = ".reading-content .page-break.no-gaps img"
    SERIES_TITLE = ".post-title > h1"
    NAV_BREADCUMBS = ".wp-manga-nav .breadcrumb li"


class ToonilyCrawler(Crawler):
    # TODO: Make this a general crawler for any site that uses wordpress madara
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Series": "/serie/<name>",
        "Chapter": "/serie/<name>/chapter-<chapter-id>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://toonily.com")
    DOMAIN: ClassVar[str] = "toonily"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["serie", _]:
                return await self.series(scrape_item)
            case ["serie", _, chapter] if chapter.startswith("chapter-"):
                return await self.chapter(scrape_item)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url, impersonate=True)

        title_tag = css.select(soup, Selector.SERIES_TITLE)
        css.decompose(title_tag, "*")
        series_title = self.create_title(css.text(title_tag))
        scrape_item.setup_as_profile(series_title)
        for new_scrape_item in self.iter_children(scrape_item, soup, Selector.CHAPTER):
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url, impersonate=True)

        *_, series_name, chapter_title = (css.text(bc) for bc in soup.select(Selector.NAV_BREADCUMBS))

        if scrape_item.type != ScrapeItemType.PROFILE:
            series_title = self.create_title(series_name)
            scrape_item.append_folders(series_title)

        scrape_item.setup_as_album(chapter_title)
        scrape_item.uploaded_at = json_ld.date_published(soup)

        for link in self.iter_urls(soup, Selector.IMAGE, "src"):
            self.create_eager_task(self.direct_file(scrape_item, link))
            scrape_item.add_children()
