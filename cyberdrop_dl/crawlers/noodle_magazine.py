from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PLAYLIST_SELECTOR = "script:-soup-contains('window.playlist')"
METADATA_SELECTOR = "script[type='application/ld+json']"
SEARCH_STRING_SELECTOR = "div.mh_line > h1.c_title"
VIDEOS_SELECTOR = "div#list_videos a.item_link"


class Source(NamedTuple):
    resolution: Resolution
    file: str

    @staticmethod
    def new(source_dict: dict[str, Any]) -> Source:
        resolution = Resolution.parse(source_dict["label"])
        return Source(resolution, source_dict["file"])


PRIMARY_URL = AbsoluteHttpURL("https://noodlemagazine.com")


class NoodleMagazineCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Search": "/video/<search_query", "Video": "/watch/<video_id>"}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "noodlemagazine"
    FOLDER_DOMAIN: ClassVar[str] = "NoodleMagazine"
    _DOWNLOAD_SLOTS: ClassVar[int | None] = 2
    _RATE_LIMIT = 1, 3

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "video" in scrape_item.url.parts:
            return await self.search(scrape_item)
        elif "watch" in scrape_item.url.parts:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        init_page = int(scrape_item.url.query.get("p") or 1)
        seen_urls: set[AbsoluteHttpURL] = set()
        for page in itertools.count(1, init_page):
            n_videos = 0
            page_url = scrape_item.url.with_query(p=page)
            soup = await self.request_soup(page_url, impersonate=True)

            if not title:
                search_string: str = css.select_one_get_text(soup, SEARCH_STRING_SELECTOR)
                title = search_string.rsplit(" videos", 1)[0]
                title = self.create_title(f"{title} [search]")
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                if new_scrape_item.url not in seen_urls:
                    seen_urls.add(new_scrape_item.url)
                    n_videos += 1
                    self.create_task(self.run(new_scrape_item))

            if n_videos < 24:
                break

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        soup = await self.request_soup(scrape_item.url, impersonate=True)

        metadata_text = css.select_one(soup, METADATA_SELECTOR).get_text()
        metadata = json.loads(metadata_text.strip())
        playlist = soup.select_one(PLAYLIST_SELECTOR)
        if not playlist:
            raise ScrapeError(404)

        playlist_data = json.loads(get_text_between(playlist.text, "window.playlist = ", ";\nwindow.ads"))
        best_source = max(Source.new(source) for source in playlist_data["sources"])
        title: str = css.select_one(soup, "title").get_text().split(" watch online")[0]

        scrape_item.possible_datetime = self.parse_date(metadata["uploadDate"], "%Y-%m-%d")
        content_url = self.parse_url(metadata["contentUrl"])
        filename, ext = self.get_filename_and_ext(content_url.name)
        video_id = filename.removesuffix(ext)
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=best_source.resolution)
        src_url = self.parse_url(best_source.file)
        await self.handle_file(
            content_url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=src_url
        )
