from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, Self

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_valid_dict

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


NEXT_PAGE_SELECTOR = ""
JS_VIDEO_INFO_SELECTOR = "script#initials-script"
GALLERY_TITLE_SELECTOR = "meta [property='og:image:alt']"
IMAGE_SELECTOR = "div.fotorama__img a"


class Format(NamedTuple):
    height: int
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Video:
    id: str
    id_hash_slug: str
    title: str
    formats: tuple[Format, ...]
    mp4_file: str
    created: int
    url: str

    @classmethod
    def from_dict(cls, info_dict: dict) -> Self:
        sources: dict = info_dict.get("sources") or {}
        mp4_sources: dict[str, dict] = sources.get("mp4") or {}
        mp4_file: str = info_dict.get("mp4File") or ""
        formats = [Format(0, mp4_file)]

        for resolution, details in mp4_sources.items():
            height = int(resolution.removesuffix("p"))
            url: str = details["link"]
            formats.append(Format(height, url))

        valid_vars = get_valid_dict(cls, info_dict)
        return cls(
            **valid_vars,
            url=info_dict["pageURL"],
            id_hash_slug=info_dict["idHashSlug"],
            mp4_file=mp4_file,
            formats=tuple(formats),
        )


class XhamsterCrawler(Crawler):
    primary_base_domain = URL("https://xhamster.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xhamster", "xHamster")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        ## TODO: user profile support, categories and tags
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        json_info = get_window_initials_json(soup)
        del soup
        gallery: dict = json_info.get("photosGalleryModel") or json_info["galleryModel"]
        log_debug(gallery)
        images: list[dict] = gallery["photos"]
        gallery_id = gallery["id"]
        title = f"{gallery['title']} [gallery]"
        scrape_item.setup_as_album(title, album_id=gallery_id)
        scrape_item.possible_datetime = gallery["created"]

        n_images = gallery["quantity"]
        padding = max(3, len(str(n_images)))

        is_single_image = gallery_id != scrape_item.url.name
        single_image_id = int(scrape_item.url.name) if is_single_image else None
        for index, image in enumerate(images, 1):
            if is_single_image and single_image_id != image["id"]:
                continue
            link = self.parse_url(image["imageURL"])
            page_url = self.parse_url(image["pageURL"])

            filename, ext = self.get_filename_and_ext(link.name)
            custom_filename = f"{index:0{padding}d} - {filename}"
            new_scrape_item = scrape_item.create_child(page_url)
            await self.handle_file(link, new_scrape_item, filename, ext, custom_filename=custom_filename)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        json_info = get_window_initials_json(soup)
        del soup
        video_info = json_info["videoModel"]
        log_debug(video_info)
        video = Video.from_dict(video_info)
        canonical_url = self.parse_url(video.url)
        best_format = max(video.formats)
        if not best_format.url:
            raise ScrapeError(422, message="No video source found")

        scrape_item.url = canonical_url
        scrape_item.possible_datetime = video.created
        resolution = f"{best_format.height}p" if best_format.height else "Unknown"
        link = self.primary_base_domain / "movies" / video.id_hash_slug / "download" / resolution
        debrid_link = self.parse_url(best_format.url)

        filename = f"{video.id_hash_slug}.mp4"
        filename, ext = self.get_filename_and_ext(filename)
        custom_filename = f"{video.title} [{video.id_hash_slug}][{resolution}]{ext}"
        custom_filename, _ = self.get_filename_and_ext(custom_filename)
        await self.handle_file(
            link, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=debrid_link
        )


def get_window_initials_json(soup: BeautifulSoup) -> dict[str, dict]:
    js_code = get_javascript_text(soup)
    return get_json_from_js(js_code)


def get_javascript_text(soup: BeautifulSoup) -> str:
    info_js_script = soup.select_one(JS_VIDEO_INFO_SELECTOR)
    info_js_script_text = info_js_script.text if info_js_script else None
    if not info_js_script_text:
        raise ScrapeError(422)
    return info_js_script_text


def get_json_from_js(js_code: str) -> dict[str, dict]:
    json_text = js_code.split("=", 1)[-1].removesuffix(";")
    json_dict = javascript.parse_json_to_dict(json_text)
    javascript.clean_dict(json_dict)
    return json_dict
