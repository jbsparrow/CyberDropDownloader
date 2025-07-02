from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, NamedTuple

from pydantic import AliasPath, Field, PlainValidator

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, parse_url

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://xhamster.com/")


class Selectors:
    JS_VIDEO_INFO = "script#initials-script"
    VIDEO = "a.video-thumb__image-container"
    GALLERY = "a.gallery-thumb__link"
    NEXT_PAGE = "a[data-page='next']"


_SELECTORS = Selectors()


HttpURL = Annotated[AbsoluteHttpURL, PlainValidator(partial(parse_url, relative_to=PRIMARY_URL))]


class XhamsterCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/videos/<video_title>",
        "User": "/users/<user_name>",
        "Creator": "/creatos/<creator_name>",
        "Gallery": "photos/gallery/<gallery_name>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "xhamster"
    FOLDER_DOMAIN: ClassVar[str] = "xHamster"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        if any(p in scrape_item.url.parts for p in ("creators", "users")):
            return await self.profile(scrape_item)
        if any(p in scrape_item.url.parts for p in ("movies", "videos")):
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        profile_type, username = scrape_item.url.parts[1:3]
        title = self.create_title(f"{username} [{profile_type.removesuffix('s')}]")
        scrape_item.setup_as_profile(title)
        is_user = "users" in scrape_item.url.parts
        last_part = "videos" if is_user else "exclusive"
        base_url = PRIMARY_URL / profile_type / username

        all_paths = ("videos", "photos")
        paths_to_scrape = next(((p,) for p in all_paths if p in scrape_item.url.parts), all_paths)

        if "videos" in paths_to_scrape:
            videos_url = base_url / last_part
            await self.process_children(scrape_item, videos_url, _SELECTORS.VIDEO, last_part)

        if is_user and "photos" in paths_to_scrape:
            gallerys_url = base_url / "photos"
            await self.process_children(scrape_item, gallerys_url, _SELECTORS.GALLERY, "galleries")

    @error_handling_wrapper
    async def process_children(self, scrape_item: ScrapeItem, url: URL, selector: str, name: str) -> None:
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector, new_title_part=name):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        json_info = await self.get_model_details(scrape_item.url, "photosGalleryModel", "galleryModel")
        gallery = Gallery(**json_info)
        title = f"{gallery.title} [gallery]"
        scrape_item.setup_as_album(title, album_id=gallery.id)
        scrape_item.possible_datetime = gallery.created

        padding = max(3, len(str(gallery.quantity)))
        for index, image in enumerate(gallery.photos, 1):
            filename, ext = self.get_filename_and_ext(image.url.name)
            # TODO: Adding an index prefix should be handled by `create_custom_filename`
            custom_filename = f"{str(index).zfill(padding)} - {filename.removesuffix(ext)}"
            custom_filename = self.create_custom_filename(custom_filename, ext, file_id=image.id)
            new_scrape_item = scrape_item.create_child(image.page_url)
            await self.handle_file(image.url, new_scrape_item, filename, ext, custom_filename=custom_filename)
            scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        json_info = await self.get_model_details(scrape_item.url, "videoModel")
        video = Video(**json_info)

        scrape_item.url = video.page_url
        scrape_item.possible_datetime = video.created
        _, resolution, download_url = max(video.get_formats())
        link = PRIMARY_URL / "movies" / video.id / "download" / resolution
        filename, ext = self.get_filename_and_ext(f"{video.id}.mp4")
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=resolution)
        await self.handle_file(
            link, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=download_url
        )

    async def get_model_details(self, url: URL, *model_name_choices: str) -> dict:
        model_names = model_name_choices or []

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, url)

        json_info = get_window_initials_json(soup)
        del soup

        def get_model_value():
            for model_name in model_names:
                if (value := json_info.get(model_name)) is not None:
                    return value

        json_info = get_model_value() or json_info
        log_debug(json_info)
        return json_info


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_window_initials_json(soup: BeautifulSoup) -> dict[str, dict]:
    js_script = soup.select_one(_SELECTORS.JS_VIDEO_INFO)
    js_code: str = str(js_script)
    json_text: str = get_text_between(js_code, "window.initials=", "</script>").removesuffix(";").strip()
    return json.loads(json_text)


class Format(NamedTuple):
    height: int
    resolution: str
    url: URL


class XHamsterItem(AliasModel):
    id: str = Field(alias="idHashSlug")
    page_url: HttpURL = Field(alias="pageURL")
    created: int = 0


class Image(XHamsterItem):
    url: HttpURL = Field(alias="imageURL")


class Gallery(XHamsterItem):
    title: str
    photos: list[Image]
    quantity: int


class Video(XHamsterItem):
    title: str
    mp4_file: HttpURL = Field(alias="mp4File")
    mp4_sources: dict[str, Any] = Field({}, validation_alias=AliasPath("sources", "mp4"))

    def get_formats(self) -> Generator[Format]:
        yield Format(0, "", self.mp4_file)
        for resolution, details in self.mp4_sources.items():
            height = int(resolution.removesuffix("p"))
            link: str = details["link"] if isinstance(details, dict) else details
            url = parse_url(link, relative_to=PRIMARY_URL)
            yield Format(height, f"{height}p", url)
