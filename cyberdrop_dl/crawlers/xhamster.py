from __future__ import annotations

import base64
import dataclasses
import itertools
import json
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, parse_url, xor_decrypt

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://xhamster.com/")
_ALLOW_AV1 = False
_ALLOW_HLS = False
_DECRYPTION_KEY = b"xh7999"


class Selector:
    VIDEO = "a.video-thumb__image-container"
    GALLERY = "a.gallery-thumb__link"
    NEXT_PAGE = "a[data-page='next']"


def _parse_url(url: str) -> AbsoluteHttpURL:
    if url.startswith("eG9y"):
        url = xor_decrypt(base64.b64decode(url)[4:], _DECRYPTION_KEY)
    return parse_url(url, relative_to=_PRIMARY_URL)


class XhamsterCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": "/videos/<title>",
        "User": (
            "/users/<user_name>",
            "/users/profiles/<user_name>",
        ),
        "User Videos": "/users/<user_name>/videos",
        "User Galleries": "/users/<user_name>/photos",
        "Creator": "/creators/<creator_name>",
        "Creator Videos": "/creators/<creator_name>/exclusive",
        "Creator Galleries": "/creators/<creator_name>/photos",
        "Gallery": "/photos/gallery/<gallery_name_or_id>",
    }
    PRIMARY_URL = _PRIMARY_URL
    NEXT_PAGE_SELECTOR = Selector.NEXT_PAGE
    DOMAIN = "xhamster"
    FOLDER_DOMAIN = "xHamster"

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(4, 1)
        self._seen_hosts: set[str] = set()

    def _disable_ai_title_translations(self, url: AbsoluteHttpURL) -> None:
        if url.host not in self._seen_hosts:
            self.update_cookies({"lang": "en", "video_titles_translation": "0"}, url.origin())
            self._seen_hosts.add(url.host)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["photos", "gallery", _]:
                return await self.gallery(scrape_item)
            case ["videos", _]:
                return await self.video(scrape_item)
            case ["users" | "creators" as type_, _, *rest]:
                match rest:
                    case []:
                        return await self.profile(scrape_item)
                    case ["photos"]:
                        return await self.profile(scrape_item, download_videos=False)
                    case ["videos"] if type_ == "users":
                        return await self.profile(scrape_item, download_photos=False)
                    case ["exclusive"] if type_ == "creators":
                        return await self.profile(scrape_item, download_photos=False)
                    case _:
                        raise ValueError
            case _:
                raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case ["photos", "gallery", name, *rest] if rest:
                return url.origin() / "photos/gallery" / name
            case ["users", "profiles", name]:
                return url.origin() / "users" / name
            case _:
                return url

    @error_handling_wrapper
    async def profile(
        self,
        scrape_item: ScrapeItem,
        *,
        download_photos: bool = True,
        download_videos: bool = True,
    ) -> None:
        url_type, username = scrape_item.url.parts[1:3]
        canonical_url = scrape_item.url.origin() / url_type / username
        initials = await self._get_window_initials(canonical_url)
        is_creator = url_type == "creators"
        if is_creator:
            info: dict[str, Any] = initials["infoComponent"]["displayUserModel"]
            web_page_url = self.parse_url(info["pageURL"])
            has_videos = bool(initials["infoComponent"].get("pornstarTop", {}).get("videoCount", 0))
            has_galleries = bool(initials.get("galleriesComponent", {}).get("galleriesTotal", 0))

        else:
            info = initials["displayUserModel"]
            web_page_url = canonical_url
            has_videos = bool(initials["counters"]["videos"])
            has_galleries = bool(initials["counters"]["galleries"])

        # every creator is an user, but not every user is a creator
        # the creator's name and the user_name are different for the same account
        # we will ignore the creator's name and always use the user_name

        creator_name: str | None = info.get("pageTitle")  # noqa: F841
        user_name: str = info.get("displayName") or info["name"]
        title = self.create_title(f"{user_name} [user]")
        scrape_item.setup_as_profile(title)

        if has_videos and download_videos:
            videos_url = web_page_url / "videos"
            await self._iter_profile_pages(scrape_item, videos_url, Selector.VIDEO, "videos")

        if has_galleries and download_photos:
            gallerys_url = web_page_url / "photos"
            await self._iter_profile_pages(scrape_item, gallerys_url, Selector.GALLERY, "galleries")

    @error_handling_wrapper
    async def _iter_profile_pages(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, selector: str, name: str
    ) -> None:
        async for soup in self.web_pager(url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, selector, new_title_part=name):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        initials = await self._get_window_initials(scrape_item.url)
        page_details: dict[str, Any] = initials["galleryPage"]
        gallery: dict[str, Any] = page_details["galleryModel"]
        gallery_id = str(gallery["id"])
        title = self.create_title(f"{gallery['title']} [gallery]", gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        scrape_item.possible_datetime = gallery["created"]

        results = await self.get_album_results(gallery_id)
        n_pages: int = page_details["paginationProps"]["lastPageNumber"]
        index: int = 0
        images: list[dict[str, Any]] = initials["photosGalleryModel"]["photos"]

        for next_page in itertools.count(2):
            for img in images:
                img["index"] = index = index + 1
                self._handle_img(scrape_item, img, results)

            if next_page > n_pages:
                break

            next_page_url = scrape_item.url / str(next_page)
            initials = await self._get_window_initials(next_page_url)
            images = initials["photosGalleryModel"]["photos"]

    def _handle_img(self, scrape_item: ScrapeItem, img: dict[str, Any], results: dict[str, int]):
        src, page_url = self.parse_url(img["imageURL"]), self.parse_url(img["pageURL"])
        if self.check_album_results(src, results):
            return

        _, ext = self.get_filename_and_ext(src.name)
        stem = f"{str(img['index']).zfill(3)} - {src.name.removesuffix(ext)}"
        filename = self.create_custom_filename(stem, ext, file_id=img["id"])
        new_scrape_item = scrape_item.create_child(page_url)
        self.create_task(self.handle_file(src, new_scrape_item, src.name, ext, custom_filename=filename))
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
            filename=video.id + ".mp4",
            custom_filename=custom_filename,
            debrid_link=video.best_mp4.url,
        )

    async def _get_window_initials(self, url: AbsoluteHttpURL) -> dict[str, Any]:
        self._disable_ai_title_translations(url)
        async with self.request_limiter:
            content = await self.client.get_text(self.DOMAIN, url)

        initials = get_text_between(content, "window.initials=", ";</script>")
        return json.loads(initials)


class Format(NamedTuple):
    resolution: int
    codec: str  #  h264 > av1
    url: AbsoluteHttpURL


@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    id: str
    title: str
    created: int
    url: AbsoluteHttpURL
    best_hls: Format | None
    best_mp4: Format


def _parse_video(initials: dict[str, Any]) -> Video:
    video: dict[str, Any] = initials["videoModel"]

    hls_sources: list[Format] = []
    mp4_sources: list[Format] = []

    sources = itertools.chain(_parse_http_sources(initials), _parse_xplayer_sources(initials))

    for src in sources:
        if src.codec == "av1" and not _ALLOW_AV1:
            continue
        if src.url.suffix == ".m3u8":
            if not _ALLOW_HLS:
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
            resolution = int(quality.removesuffix("p"))
            yield Format(resolution, codec, url)


def _parse_xplayer_sources(initials: dict[str, Any]) -> Iterable[Format]:
    xplayer_sources: dict[str, Any] = initials.get("xplayerSettings", {}).get("sources", {})
    if not xplayer_sources:
        return

    seen_urls: set[AbsoluteHttpURL] = set()

    def parse_format(format_dict: dict[str, str], codec: str):
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

            yield Format(resolution, codec, url)

    hls_sources: dict[str, dict[str, str]] = xplayer_sources.get("hls", {})
    for codec, format_dict in hls_sources.items():
        yield from parse_format(format_dict, codec)

    standard_sources: dict[str, list[dict[str, Any]]] = xplayer_sources.get("standard", {})
    for codec, formats_list in standard_sources.items():
        for format_dict in formats_list:
            yield from parse_format(format_dict, codec)
