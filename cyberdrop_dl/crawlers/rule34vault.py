from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    CONTENT = "div[class='box-grid ng-star-inserted'] a[class='box ng-star-inserted']"
    TITLE = "div[class*=title]"
    DATE = 'div[class="posted-date-full text-secondary mt-4 ng-star-inserted"]'
    VIDEO = 'div[class="con-video ng-star-inserted"] > video > source'
    IMAGE = 'img[class*="img ng-star-inserted"]'


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://rule34vault.com")


class Rule34VaultCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Post": "/post/...",
        "Playlist": "/playlists/view/...",
        "Tag": "/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "rule34vault"
    FOLDER_DOMAIN: ClassVar[str] = "Rule34Vault"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "post" in scrape_item.url.parts:
            return await self.file(scrape_item)
        if "playlists" in scrape_item.url.parts and "view" not in scrape_item.url.parts:
            raise ValueError
        return await self.playlist_or_tag(scrape_item)

    @error_handling_wrapper
    async def playlist_or_tag(self, scrape_item: ScrapeItem) -> None:
        is_playlist = "playlists" in scrape_item.url.parts
        init_page = int(scrape_item.url.query.get("page") or 1)
        title: str = ""
        for page in itertools.count(init_page):
            url = scrape_item.url.with_query(page=page)
            n_images = 0
            soup = await self.request_soup(url)

            if not title:
                if is_playlist:
                    album_id = scrape_item.url.parts[-1]
                    title_str: str = css.select_one_get_text(soup, _SELECTORS.TITLE)
                    title = self.create_title(title_str, album_id)
                    scrape_item.setup_as_album(title, album_id=album_id)
                else:
                    title = self.create_title(scrape_item.url.parts[1])
                    scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.CONTENT):
                n_images += 1
                self.create_task(self.run(new_scrape_item))

            if n_images < 30:
                break

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        canonical_url = scrape_item.url.with_query(None)
        if await self.check_complete_from_referer(canonical_url):
            return

        soup = await self.request_soup(scrape_item.url)

        if date_tag := soup.select_one(_SELECTORS.DATE):
            scrape_item.possible_datetime = self.parse_date(date_tag.text, "%b %d, %Y, %I:%M:%S %p")

        scrape_item.url = canonical_url
        media_tag = soup.select_one(_SELECTORS.VIDEO) or soup.select_one(_SELECTORS.IMAGE)
        assert media_tag
        link_str: str = css.get_attr(media_tag, "src")
        for trash in (".small", ".thumbnail", ".picsmall", ".720", ".hevc"):
            link_str = link_str.replace(trash, "")

        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
