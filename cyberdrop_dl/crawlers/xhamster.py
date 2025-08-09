from __future__ import annotations

import dataclasses
import itertools
import json
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, NamedTuple

from pydantic import Field, PlainValidator

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.models import AliasModel
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, parse_url

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://xhamster.com/")
ALLOW_HLS = False
ALLOW_AV1 = False


class Selectors:
    JS_VIDEO_INFO = "script#initials-script"
    VIDEO = "a.video-thumb__image-container"
    GALLERY = "a.gallery-thumb__link"
    NEXT_PAGE = "a[data-page='next']"


_SELECTORS = Selectors()


_parse_url = partial(parse_url, relative_to=PRIMARY_URL)

HttpURL = Annotated[AbsoluteHttpURL, PlainValidator(_parse_url)]


class XhamsterCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/videos/<video_title>",
        "User": "/users/<user_name>",
        "Creator": "/creatos/<creator_name>",
        "Gallery": "/photos/gallery/<gallery_name>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "xhamster"
    FOLDER_DOMAIN: ClassVar[str] = "xHamster"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["photos", "gallery", _]:
                return await self.gallery(scrape_item)
            case ["movies" | "videos", _]:
                return await self.video(scrape_item)
            case ["creators" | "users", _]:
                return await self.profile(scrape_item)
            case ["gallery"]:
                return await self.gallery(scrape_item)
            case _:
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
    async def process_children(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, selector: str, name: str) -> None:
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector, new_title_part=name):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        json_info = await self._get_window_initials(scrape_item.url, "photosGalleryModel", "galleryModel")
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

        initials = await self._get_window_initials(scrape_item.url)

        video = _parse_video(initials)
        scrape_item.possible_datetime = video.created
        custom_filename = self.create_custom_filename(
            video.title,
            ".mp4",
            file_id=video.id,
            video_codec=video.best_mp4.codec,
            resolution=video.best_mp4.resolution,
        )
        await self.handle_file(
            video.url,
            scrape_item,
            filename=f"{video.id}.mp4",
            custom_filename=custom_filename,
            debrid_link=video.best_mp4.url,
        )

    async def _get_window_initials(self, url: AbsoluteHttpURL, *model_name_choices: str) -> dict[str, Any]:
        async with self.request_limiter:
            soup = await self.client.get_soup(self.DOMAIN, url)

        js_script = css.select_one(soup, _SELECTORS.JS_VIDEO_INFO)
        json_text = get_text_between(str(js_script), "window.initials=", ";</script>")
        return json.loads(json_text)


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


@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    id: str
    title: str
    created: int
    url: AbsoluteHttpURL
    best_hls: Format | None
    best_mp4: Format


def _parse_video(initials: dict[str, Any]):
    video: dict[str, Any] = initials["videoModel"]

    hls_sources: list[Format] = []
    mp4_sources: list[Format] = []

    sources = itertools.chain(_parse_http_sources(initials), _parse_xplayer_sources(initials))

    for src in sources:
        if src.codec == "av1" and not ALLOW_AV1:
            continue
        if src.url.suffix == ".m3u8":
            if not ALLOW_HLS:
                continue
            hls_sources.append(src)
        else:
            mp4_sources.append(src)

    return Video(
        id=video["idHashSlug"],
        title=video["title"],
        created=video["created"],
        url=_parse_url(video["pageURL"]),
        best_hls=max(hls_sources, default=None),
        best_mp4=max(mp4_sources),
    )


class Format(NamedTuple):
    codec: str  # av1 > h264
    resolution: int
    url: AbsoluteHttpURL


def _parse_http_sources(initials: dict[str, Any]) -> Iterable[Format]:
    seen_urls: set[AbsoluteHttpURL] = set()

    http_sources: dict[str, dict[str, str]] = initials["videoModel"].get("sources") or {}
    if not http_sources:
        return

    for codec, formats_dict in http_sources.items():
        for quality, url in formats_dict.items():
            if codec == "download":
                continue

            url = _parse_url(url)
            if url in seen_urls:
                continue

            seen_urls.add(url)
            yield Format(codec, int(quality.removesuffix("p")), url)


def _parse_xplayer_sources(initials: dict[str, Any]) -> Iterable[Format]:
    xplayer_sources: dict[str, Any] = initials.get("xplayerSettings", {}).get("sources", {})
    if not xplayer_sources:
        return

    seen_urls: set[AbsoluteHttpURL] = set()

    def parse_format_dict(format_dict: dict[str, str], codec: str):
        for key in ("url", "fallback"):
            url = format_dict.get(key)
            if not url:
                continue

            url = _parse_url(url)
            if url in seen_urls:
                continue

            seen_urls.add(url)
            if url.suffix == ".m3u8":
                resolution = 0
            else:
                quality: str = format_dict.get("quality") or format_dict["label"]
                resolution = int(quality.removesuffix("p"))

            yield Format(codec, resolution, url)

    hls_sources: dict[str, dict[str, str]] = xplayer_sources.get("hls") or {}
    for codec, format_dict in hls_sources.items():
        yield from parse_format_dict(format_dict, codec)

    standard_sources: dict[str, list[dict[str, Any]]] = xplayer_sources.get("standard") or {}
    for codec, formats_list in standard_sources.items():
        for format_dict in formats_list:
            yield from parse_format_dict(format_dict, codec)
