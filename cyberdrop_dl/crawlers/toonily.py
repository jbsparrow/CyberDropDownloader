from __future__ import annotations

from typing import ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import FILE_HOST_PROFILE, AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper


class Selector:
    CHAPTER = ".wp-manga-chapter a"
    IMAGE = ".reading-content .page-break.no-gaps img"
    SERIES_TITLE = ".post-title > h1"
    CHAPTER_TITLE = "#chapter-heading"


class ToonilyCrawler(Crawler):
    # TODO: Make this a general crawler for any site that uses wordpress madara
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Serie": "/serie/<name>",
        "Charpter": "/serie/<name>/chapter-<chapter-id>",
    }
    PRIMARY_URL = AbsoluteHttpURL("https://toonily.com")
    DOMAIN = "toonily"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["serie", _, *rest]:
                match rest:
                    case []:
                        return await self.series(scrape_item)
                    case [chapter] if chapter.startswith("chapter-"):
                        return await self.chapter(scrape_item)

        raise ValueError

    @error_handling_wrapper
    async def series(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        title_tag = css.select_one(soup, Selector.SERIES_TITLE)
        css.decompose(title_tag, "*")
        series_title = self.create_title(css.get_text(title_tag))
        scrape_item.setup_as_profile(series_title)
        for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.CHAPTER):
            self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def chapter(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        series_name, chapter_title = css.select_one_get_text(soup, Selector.CHAPTER_TITLE).split(" - ", 1)
        if scrape_item.type != FILE_HOST_PROFILE:
            series_title = self.create_title(series_name)
            scrape_item.add_to_parent_title(series_title)

        scrape_item.setup_as_album(chapter_title)
        iso_date = css.get_json_ld(soup)["@graph"][0]["datePublished"]
        scrape_item.possible_datetime = self.parse_iso_date(iso_date)

        for _, link in self.iter_tags(soup, Selector.IMAGE, "data-src"):
            filename, ext = self.get_filename_and_ext(link.name)
            self.create_task(self.handle_file(link, scrape_item, filename, ext))
            scrape_item.add_children()
