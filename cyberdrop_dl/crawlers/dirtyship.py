from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    VIDEO = "video#fp-video-0 > source"
    FLOWPLAYER_VIDEO = "div.freedomplayer"
    PLAYLIST_ITEM = "li.thumi > a"
    GALLERY_TITLE = "div#album p[style='text-align: center;']"
    GALLERY_ALTERNATIVE_TITLE = "h1.singletitle"
    GALLERY_THUMBNAILS = "div.gallery_grid img.gallery-img"
    GALLERY_ALTERNATIVE_THUMBNAILS = "div#gallery-1 img"
    GALLERY_DECODING_ASYNC = "div#album img[decoding='async']"
    SINGLE_PHOTO = "div.resolutions a"


_SELECTORS = Selectors()


class Format(NamedTuple):
    resolution: int | None
    url: AbsoluteHttpURL


PRIMARY_URL = AbsoluteHttpURL("https://dirtyship.com")


class DirtyShipCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Category": "/category/...",
        "Tag": "/tag/...",
        "Video": "/<video_name>",
        "Gallery": "/gallery/...",
        "Photo": "/gallery/.../...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a.page-next"
    DOMAIN: ClassVar[str] = "dirtyship"
    FOLDER_DOMAIN: ClassVar[str] = "DirtyShip"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in ("tag", "category")):
            return await self.playlist(scrape_item)
        if "gallery" in scrape_item.url.parts:
            if len(scrape_item.url.parts) >= 4:
                return await self.photo(scrape_item)
            else:
                return await self.gallery(scrape_item)
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return
        if not scrape_item.url.suffix == ".jpg":
            soup = await self.request_soup(scrape_item.url)
            url = self.parse_url(
                next(css.get_attr(a, "href") for a in soup.select(_SELECTORS.SINGLE_PHOTO) if "full" in a.get_text())
            )
        else:
            url = scrape_item.url
        filename, ext = self.get_filename_and_ext(url.name)
        await self.handle_file(url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title_tag = soup.select_one(_SELECTORS.GALLERY_TITLE) or soup.select_one(
                    _SELECTORS.GALLERY_ALTERNATIVE_TITLE
                )
                assert title_tag
                title: str = title_tag.get_text(strip=True)
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            thumbnails = (
                soup.select(_SELECTORS.GALLERY_THUMBNAILS)
                or soup.select(_SELECTORS.GALLERY_ALTERNATIVE_THUMBNAILS)
                or soup.select(_SELECTORS.GALLERY_DECODING_ASYNC)
            )

            for img in thumbnails:
                url = (
                    css.get_attr(img, "src")
                    if img.get("decoding") == "async"
                    else get_highest_resolution_picture(css.get_attr(img, "srcset"))
                )
                if not url:
                    raise ScrapeError(404)
                url = self.parse_url(url)
                filename, ext = self.get_filename_and_ext(url.name)
                await self.handle_file(url, scrape_item, filename, ext)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title: str = css.select_one_get_text(soup, "title")
                title = title.split("Archives - DirtyShip")[0]
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PLAYLIST_ITEM):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)

        title: str = css.select_one_get_text(soup, "title")
        title = title.split(" - DirtyShip")[0]
        videos = soup.select(_SELECTORS.VIDEO)

        def get_formats():
            for video in videos:
                link_str: str = css.get_attr(video, "src")
                if link_str.startswith("type="):
                    continue
                res: str = css.get_attr(video, "title")
                link = self.parse_url(link_str)
                yield (Format(int(res), link))

        formats = set(get_formats())
        if not formats:
            formats = self.get_flowplayer_sources(soup)
        if not formats:
            raise ScrapeError(422, message="No video source found")

        res, link = sorted(formats)[-1]
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext, resolution=res)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    def get_flowplayer_sources(self, soup: BeautifulSoup) -> set[Format]:
        flow_player = soup.select_one(_SELECTORS.FLOWPLAYER_VIDEO)
        data_item: str | None = css.get_attr_or_none(flow_player, "data-item") if flow_player else None
        if not data_item:
            return set()
        data_item = data_item.replace(r"\/", "/")
        json_data = json.loads(data_item)
        sources = json_data["sources"]
        return {Format(None, self.parse_url(s["src"])) for s in sources}


"""~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""


def get_highest_resolution_picture(srcset: str) -> str | None:
    """
    Parses a srcset string and returns the URL with the highest resolution (width).
    """
    candidates = []
    for item in srcset.split(","):
        parts = item.strip().split()
        if len(parts) == 2:
            url, width = parts
            try:
                width = int(width.rstrip("w"))
                candidates.append((width, url))
            except ValueError:
                continue
    return max(candidates)[1] if candidates else None
