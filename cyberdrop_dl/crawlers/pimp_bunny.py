from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers._kvs import extract_kvs_video
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures import AbsoluteHttpURL, Resolution
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, filter_query

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_PER_PAGE: int = 1000


@dataclasses.dataclass(slots=True)
class KVSVideo:
    id: str
    title: str
    url: AbsoluteHttpURL
    resolution: Resolution


class Selector:
    UNAUTHORIZED = "div.video-holder:-soup-contains('This video is a private video')"
    VIDEO_VARS = "script:-soup-contains('video_title:')"
    VIDEOS = "div#list_videos_common_videos_list_items a"
    MODEL_NAME = "div.pb-model-title .model-name"
    ITEM = "a[href].pb-item-link"
    ALBUM_TAB = "a.pb-heading-h2[href*='/albums/models/']"
    ALBUM_TITLE = ".pb-view-album-title h1"


def _pagination_query(url: AbsoluteHttpURL) -> dict[str, Any]:
    per_page_params = {
        "albums_per_page" if "albums" in url.parts else "videos_per_page": _PER_PAGE,
    }
    return filter_query(url.update_query(per_page_params).query, ("sort_by", "post_date"), "duration")


class PimpBunnyCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/videos/...",
        "Models": "/onlyfans-models/<model_name>",
        "Model Albums": "/albums/models/<model_name>",
        "Album": "/albums/<album_name>",
        "Category": "/categories/<category>",
        "Tag": "/tags/<tag>",
    }

    DOMAIN: ClassVar[str] = "pimpbunny.com"
    FOLDER_DOMAIN: ClassVar[str] = "PimpBunny"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://pimpbunny.com")
    DEFAULT_TRIM_URLS: ClassVar[bool] = False
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".pb-pagination-list .next a[href]"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["videos", _, *_]:
                return await self.video(scrape_item)
            case ["onlyfans-models", model_name, *_]:
                return await self.model(scrape_item, model_name)
            case ["albums", "models", model_name, *_]:
                return await self.model_albums(scrape_item, model_name)
            case ["albums", name, *_]:
                return await self.album(scrape_item, name)
            case ["categories" as type_, name, *_]:
                return await self.collection(scrape_item, type_, name)
            case ["tags" as type_, name, *_]:
                return await self.collection(scrape_item, type_, name)
            case _:
                raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: str, slug: str) -> None:
        url = scrape_item.url.origin() / collection_type / slug / ""
        title = self.create_title(f"{slug} [{collection_type}]")
        scrape_item.setup_as_album(title)

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(url.with_query(query)):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def model(self, scrape_item: ScrapeItem, model_name: str) -> None:
        model_url = scrape_item.url.origin() / "onlyfans-models" / model_name / ""
        name: str = ""

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(model_url.with_query(query)):
            if not name:
                name = css.select_one_get_text(soup, Selector.MODEL_NAME)
                scrape_item.setup_as_profile(self.create_title(f"{name} [model]"))

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

        has_albums = soup.select_one(Selector.ALBUM_TAB)
        if has_albums:
            await self.model_albums(scrape_item, model_name)

    @error_handling_wrapper
    async def model_albums(self, scrape_item: ScrapeItem, model_name: str) -> None:
        albums_url = scrape_item.url.origin() / "albums/models" / model_name / ""
        name: str = ""

        query = _pagination_query(scrape_item.url)
        async for soup in self.web_pager(albums_url.with_query(query)):
            if not name:
                name = css.select_one_get_text(soup, Selector.MODEL_NAME)
                if name not in scrape_item.parent_title:
                    scrape_item.setup_as_profile(self.create_title(f"{name} [model]"))

            for _, new_scrape_item in self.iter_children(scrape_item, soup, Selector.ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self.request_soup(scrape_item.url)
        video = extract_kvs_video(self, soup)
        custom_filename = self.create_custom_filename(
            video.title, video.url.suffix, file_id=video.id, resolution=video.resolution
        )
        scrape_item.possible_datetime = self.parse_iso_date(css.get_json_ld_date(soup))
        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.url.name,
            video.url.suffix,
            custom_filename=custom_filename,
            debrid_link=video.url,
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, name: str) -> None:
        album_url = scrape_item.url.origin() / "albums" / name / ""
        title: str = ""
        async for soup in self.web_pager(album_url):
            if not title:
                title = css.select_one_get_text(soup, Selector.ALBUM_TITLE)
                scrape_item.setup_as_album(self.create_title(f"{title} [album]"))

            for _, image in self.iter_tags(soup, Selector.ITEM):
                self.create_task(self.direct_file(scrape_item, image))
                scrape_item.add_children()
