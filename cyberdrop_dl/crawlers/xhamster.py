from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Annotated, NamedTuple

from pydantic import AfterValidator, Field
from yarl import URL

from cyberdrop_dl.config_definitions.custom.converters import convert_to_yarl
from cyberdrop_dl.config_definitions.custom.types import AliasModel, ParsedHttpStrURL
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils import javascript
from cyberdrop_dl.utils.logger import log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, parse_url

if TYPE_CHECKING:
    from collections.abc import Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

PRIMARY_BASE_DOMAIN = URL("https://xhamster.com/")
NEXT_PAGE_SELECTOR = ""
JS_VIDEO_INFO_SELECTOR = "script#initials-script"


ParsedHttpURL = Annotated[ParsedHttpStrURL, AfterValidator(partial(convert_to_yarl, relative_to=PRIMARY_BASE_DOMAIN))]


class XhamsterCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xhamster", "xHamster")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        ## TODO: user profile support, categories and tags
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        if "user" in scrape_item.url.parts:
            return await self.user(scrape_item)
        return await self.video(scrape_item)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        raise NotImplementedError

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        # async with self.request_limiter:
        #    soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        # json_info = await self.get_model_details(scrape_item.url, "displayUserModel")

        # videos_url = self.primary_base_domain / "user" / username / "videos"
        # if videos_url:
        #    pass
        raise NotImplementedError

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
            custom_filename = f"{index:0{padding}d} - {filename.removesuffix(ext)} [{image.id}]{ext}"
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
        link = PRIMARY_BASE_DOMAIN / "movies" / video.id / "download" / resolution

        filename, ext = self.get_filename_and_ext(f"{video.id}.mp4")
        custom_filename, _ = self.get_filename_and_ext(f"{video.title} [{video.id}][{resolution}]{ext}")
        await self.handle_file(
            link, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=download_url
        )

    async def get_model_details(self, url: URL, *model_name_choices: str) -> dict:
        model_names = model_name_choices or []

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, url)

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
    js_script = soup.select_one(JS_VIDEO_INFO_SELECTOR)
    js_code: str = str(js_script)
    json_text: str = get_text_between(js_code, "window.initials=", "</script>").removesuffix(";").strip()
    return javascript.parse_json_to_dict(json_text)


class Format(NamedTuple):
    height: int
    resolution: str
    url: URL


class XHamsterItem(AliasModel):
    id: str = Field(alias="idHashSlug")
    page_url: ParsedHttpURL = Field(alias="pageURL")
    created: int = 0


class Image(XHamsterItem):
    url: ParsedHttpURL = Field(alias="imageURL")


class Gallery(XHamsterItem):
    title: str
    photos: list[Image]
    quantity: int


class Video(XHamsterItem):
    title: str
    mp4_file: ParsedHttpURL = Field(alias="mp4File")
    sources: dict = Field({})

    def get_formats(self) -> Generator[Format]:
        mp4_sources: dict[str, str] = self.sources.get("mp4") or {}
        yield Format(0, "Unknown", self.mp4_file)
        for resolution, details in mp4_sources.items():
            height = int(resolution.removesuffix("p"))
            link: str = details["link"] if isinstance(details, dict) else details
            url = parse_url(link, relative_to=PRIMARY_BASE_DOMAIN)
            yield Format(height, f"{height}p", url)
