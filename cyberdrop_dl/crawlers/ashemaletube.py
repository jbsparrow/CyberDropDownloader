from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, extr_text, json_ld, m3u8
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.mediaprops import Resolution
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    PROFILE_VIDEOS = "div.sub-content div.media-item__inner > a[data-video-preview]"
    SEARCH_VIDEOS = "div.main-content div.media-item__inner > a[data-video-preview]"
    USER_NAME = "h1.username"
    PLAYLIST_VIDEOS = "a.playlist-video-item__thumbnail"
    JS_PLAYER = "script:-soup-contains('var playerConfig =')"
    LOGIN_REQUIRED = "div.loginLinks:-soup-contains('To watch this video please')"
    IMAGE_ITEM = "div.imgItem"
    ALBUM_IMAGES = "div.gallery-detail div.thumb"
    ALBUM_TITLE = "div.prepositions-wrapper h1"
    GALLERY_ALBUM = "div.profile-content div.galItem > a"
    NEXT_PAGE = "a.rightKey"


class CollectionType(StrEnum):
    ALBUM = "album"
    MODEL = "model"
    PLAYLIST = "playlist"
    SEARCH = "search"
    PROFILE = "profile"


MEDIA_SELECTOR_MAP = {
    CollectionType.ALBUM: Selector.ALBUM_IMAGES,
    CollectionType.MODEL: Selector.PROFILE_VIDEOS,
    CollectionType.PLAYLIST: Selector.PLAYLIST_VIDEOS,
    CollectionType.SEARCH: Selector.SEARCH_VIDEOS,
    CollectionType.PROFILE: Selector.ALBUM_IMAGES,
}

TITLE_SELECTOR_MAP = {
    CollectionType.ALBUM: Selector.ALBUM_TITLE,
    CollectionType.MODEL: Selector.USER_NAME,
    CollectionType.PLAYLIST: "h1",
    CollectionType.SEARCH: "h1",
    CollectionType.PROFILE: Selector.USER_NAME,
}

TITLE_TRASH = "Shemale Porn Videos - Trending"
PRIMARY_URL = AbsoluteHttpURL("https://www.ashemaletube.com")


@HTTPConfig(rate_limit=(3, 10))
class AShemaleTubeCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Playlist": "/playlists/...",
        "Video": "/videos/...",
        "Model": ("/creators/...", "/model/...", "/pornstars/..."),
        "User": "/profiles/...",
    }
    DOMAIN: ClassVar[str] = "ashemaletube"
    FOLDER_DOMAIN: ClassVar[str] = "aShemaleTube"
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:  # noqa: PLR0911
        if any(p in scrape_item.url.parts for p in ("creators", "profiles", "pornstars", "model")):
            if "galleries" in scrape_item.url.parts:
                return await self.gallery(scrape_item)
            return await self.collection(scrape_item, CollectionType.MODEL)
        if "videos" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "playlists" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.PLAYLIST)
        if "search" in scrape_item.url.parts:
            return await self.collection(scrape_item, CollectionType.SEARCH)
        if "images" in scrape_item.url.parts:
            return await self.direct_file(scrape_item, scrape_item.url.with_query(None))
        if "pics" in scrape_item.url.parts:
            if len(scrape_item.url.parts) >= 5:
                return await self.image(scrape_item)
            return await self.album(scrape_item)
        if "cam" in scrape_item.url.parts:
            raise ValueError
        raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        async for soup in self.web_pager(scrape_item.url, impersonate=True):
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.GALLERY_ALBUM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        album_title = ""
        async for soup in self.web_pager(scrape_item.url, impersonate=True):
            if not album_title:
                album_title = self.create_collection_title(soup, CollectionType.ALBUM)
                scrape_item.setup_as_album(album_title)

            for thumb in soup.select(MEDIA_SELECTOR_MAP[CollectionType.ALBUM]):
                await self.proccess_image(scrape_item, thumb)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_type: CollectionType) -> None:
        collection_title = ""
        async for soup in self.web_pager(scrape_item.url, impersonate=True):
            if not collection_title:
                collection_title = self.create_collection_title(soup, collection_type)
                if collection_type == CollectionType.MODEL:
                    scrape_item.setup_as_profile(collection_title)
                else:
                    scrape_item.setup_as_album(collection_title)
            for new_scrape_item in self.iter_children(scrape_item, soup, MEDIA_SELECTOR_MAP[collection_type]):
                self.create_task(self.run(new_scrape_item))

    def create_collection_title(self, soup: BeautifulSoup, collection_type: CollectionType) -> str:
        title_elem = soup.select_one(TITLE_SELECTOR_MAP[collection_type])
        if not title_elem:
            raise ScrapeError(401)
        collection_title: str = title_elem.get_text(strip=True)
        collection_title = collection_title.replace(TITLE_TRASH, "").strip()
        return self.create_title(f"{collection_title} [{collection_type}]")

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        soup = await self.request_soup(scrape_item.url, impersonate=True)
        img_item = soup.select_one(Selector.IMAGE_ITEM)
        if not img_item:
            raise ScrapeError(404)
        await self.proccess_image(scrape_item, img_item)

    @error_handling_wrapper
    async def proccess_image(self, scrape_item: ScrapeItem, img_tag: Tag) -> None:
        if image := img_tag.select_one("img"):
            link_str: str = css.attr(image, "src")
        else:
            style: str = css.select(img_tag, "a", "style")
            link_str = extr_text(style, "url('", "');")
        url = self.parse_url(link_str).with_query(None)
        filename, ext = self.get_filename_and_ext(url.name)
        custom_filename = self.create_custom_filename(filename, ext, file_id=css.attr(img_tag, "data-image-id"))
        await self.handle_file(url, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id: str = scrape_item.url.parts[2]
        canonical_url = PRIMARY_URL / "videos" / video_id
        if await self.check_complete_from_referer(canonical_url):
            return None

        soup = await self.request_soup(scrape_item.url, impersonate=True)

        if soup.select_one(Selector.LOGIN_REQUIRED):
            raise ScrapeError(401)
        js_text = css.select_text(soup, Selector.JS_PLAYER)
        resolution, url, m3u8 = await self.parse_player_info(js_text)

        scrape_item.uploaded_at = json_ld.upload_date(soup, validate={"@type": "VideoObject"})

        title = css.select_text(soup, "title").split("- aShemaletube.com")[0].strip()
        scrape_item.url = canonical_url
        filename, ext = self.get_filename_and_ext(url.name, assume_ext=".mp4")
        custom_filename = self.create_custom_filename(title, ext, file_id=video_id, resolution=resolution)

        return await self.handle_file(
            canonical_url,
            scrape_item,
            filename,
            ext,
            custom_filename=custom_filename,
            m3u8=m3u8,
        )

    async def parse_player_info(self, script_text: str) -> tuple[Resolution, AbsoluteHttpURL, m3u8.Rendition]:
        sources = extr_text(script_text, "sources: ", "aspectRatio").strip().strip(",")
        sources_data = json.loads(sources)
        url = self.parse_url(sources_data["hlsAuto"])

        rendition, playlist_info = await self.request_m3u8_playlist(url)

        return playlist_info.resolution, url, rendition
