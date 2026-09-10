from __future__ import annotations

import base64
import codecs
import dataclasses
import itertools
import json
from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar, override

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.mediaprops import Resolution
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import extr_text, parse_url, xor_decrypt
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable

    from cyberdrop_dl.url_objects import ScrapeItem

_PRIMARY_URL = AbsoluteHttpURL("https://xhamster.com/")
_ALLOW_AV1 = False
_DECRYPTION_KEY = b"xh7999"


class Selector:
    VIDEO = "a.video-thumb__image-container"
    GALLERY = "[data-gallery-id] > a[href]"
    NEXT_PAGE = "a[data-page='next']"


def _decrypt_url(raw_url: str) -> str | None:
    if raw_url.startswith(("http", "/")):
        hex_string = AbsoluteHttpURL(raw_url).parts[1].partition(",")[0]
        decoded = _decrypt_url(hex_string)
        if decoded:
            return raw_url.replace(hex_string, decoded)
        return raw_url

    if _is_hex(raw_url):
        return _decode_hex_url(raw_url)

    try:
        decoded_url = base64.b64decode(raw_url)
        if decoded_url.startswith(b"xor_"):
            return xor_decrypt(decoded_url[4:], _DECRYPTION_KEY)
        if decoded_url.startswith(b"rot13_"):
            return codecs.decode(decoded_url[6:].decode(), "rot_13")
    except ValueError:
        pass


def _parse_url(b64_url: str) -> AbsoluteHttpURL:
    url = _decrypt_url(b64_url)
    if not url:
        raise ScrapeError(422, f"Unknown encrypted URL: {b64_url}")
    return parse_url(url, relative_to=_PRIMARY_URL)


@HTTPConfig(rate_limit=(4, 1))
class XhamsterCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/videos/<slug>-<video_id>",
            "/shorts/<slug>-<video_id>",
        ),
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
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = _PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE
    DOMAIN: ClassVar[str] = "xhamster"
    FOLDER_DOMAIN: ClassVar[str] = "xHamster"

    def __post_init__(self) -> None:
        self._seen_hosts: set[str] = set()

    def _disable_ai_title_translations(self, url: AbsoluteHttpURL) -> None:
        if url.host not in self._seen_hosts:
            self.update_cookies({"lang": "en", "video_titles_translation": "0"}, url.origin())
            self._seen_hosts.add(url.host)

    @classmethod
    @override
    def check_host_match(cls, host: str) -> bool:
        return super().check_host_match(host) and "xhamsterlive" not in host

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["photos", "gallery", _]:
                return await self.gallery(scrape_item)
            case ["videos" | "shorts", slug]:
                video_id = slug.rpartition("-")[-1]
                return await self.video(scrape_item, video_id)
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

        else:
            info = initials["displayUserModel"]
            web_page_url = canonical_url

        # every creator is an user, but not every user is a creator
        # the creator's name and the user_name are different for the same account
        # we will ignore the creator's name and always use the user_name

        _creator_name: str | None = info.get("pageTitle")
        user_name: str = info.get("displayName") or info["name"]
        title = self.create_title(f"{user_name} [user]")
        scrape_item.setup_as_profile(title)

        if download_videos:
            videos_url = web_page_url / "videos"
            await self._iter_profile_pages(scrape_item, videos_url, Selector.VIDEO, "videos")

        if download_photos:
            gallerys_url = web_page_url / "photos"
            await self._iter_profile_pages(scrape_item, gallerys_url, Selector.GALLERY, "galleries")

    @error_handling_wrapper
    async def _iter_profile_pages(
        self, scrape_item: ScrapeItem, url: AbsoluteHttpURL, selector: str, name: str
    ) -> None:
        async for soup in self.web_pager(url):
            for new_scrape_item in self.iter_children(scrape_item, soup, selector):
                new_scrape_item.append_folders(name)
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        initials = await self._get_window_initials(scrape_item.url)
        page_details: dict[str, Any] = initials["galleryPage"]
        gallery: dict[str, Any] = page_details["galleryModel"]
        gallery_id = str(gallery["id"])
        title = self.create_title(f"{gallery['title']} [gallery]", gallery_id)
        scrape_item.setup_as_album(title, album_id=gallery_id)
        scrape_item.uploaded_at = gallery["created"]

        results = await self.get_album_results(gallery_id)
        n_pages: int = page_details["paginationProps"]["lastPageNumber"]
        index: int = 0
        images: list[dict[str, Any]] = gallery["photos"]

        for next_page in itertools.count(2):
            for img in images:
                img["index"] = index = index + 1
                self._handle_img(scrape_item, img, results)

            if next_page > n_pages:
                break

            next_page_url = scrape_item.url / str(next_page)
            initials = await self._get_window_initials(next_page_url)
            images = initials["photosGalleryModel"]["photos"]

    def _handle_img(self, scrape_item: ScrapeItem, img: dict[str, Any], results: dict[str, bool]) -> None:
        src, page_url = self.parse_url(img["imageURL"]), self.parse_url(img["pageURL"])
        if self.check_album_results(src, results):
            return

        _, ext = self.get_filename_and_ext(src.name)
        stem = f"{str(img['index']).zfill(3)} - {src.name.removesuffix(ext)}"
        filename = self.create_custom_filename(stem, ext, file_id=img["id"])
        new_scrape_item = scrape_item.create_child(page_url)
        self.create_eager_task(self.handle_file(src, new_scrape_item, src.name, ext, custom_filename=filename))
        scrape_item.add_children()

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, video_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        initials = await self._get_window_initials(scrape_item.url)
        video = _parse_video(initials, video_id)
        scrape_item.uploaded_at = video.created
        m3u8 = debrid_link = None

        if best_format := video.best_mp4:
            debrid_link = video.best_mp4.url
        else:
            best_format = video.best_hls
            m3u8, _ = await self.request_m3u8_playlist(video.best_hls.url)

        filename = self.create_custom_filename(
            video.title,
            ext := ".mp4",
            file_id=video.id,
            video_codec=best_format.codec.name.lower(),
            resolution=best_format.resolution,
        )

        await self.handle_file(
            scrape_item.url,
            scrape_item,
            video.id + ext,
            custom_filename=filename,
            m3u8=m3u8,
            debrid_link=debrid_link,
            thumbnail=video.thumb,
        )

    async def _get_window_initials(self, url: AbsoluteHttpURL) -> dict[str, Any]:
        self._disable_ai_title_translations(url)
        content = await self.request_text(url)
        initials = extr_text(content, "window.initials=", ";</script>")
        return json.loads(initials)


class Codec(IntEnum):
    H264 = 1
    H265 = 2
    AV1 = 3 if _ALLOW_AV1 else 0


@dataclasses.dataclass(frozen=True, order=True, slots=True)
class Format:
    resolution: Resolution
    codec: Codec
    url: AbsoluteHttpURL


@dataclasses.dataclass(frozen=True, slots=True)
class Video:
    id: str
    title: str
    created: int
    best_hls: Format
    best_mp4: Format | None
    thumb: str | None


def _parse_video(initials: dict[str, Any], video_id: str | None = None) -> Video:
    try:
        video: dict[str, Any] = initials.get("videoModel") or initials["videoPageComponent"]["videoInfo"]["videoInfo"]
    except LookupError:
        # shorts
        video = initials["layoutPage"]["momentProps"]

    hls_sources: list[Format] = []
    mp4_sources: list[Format] = []

    for name, allow_mp4 in [
        ("xplayerSettings2", True),
        ("xplayerSettings", False),
    ]:
        xplayer_sources: dict[str, Any] = initials.get(name, {}).get("sources", {}) or {}

        for src in _parse_xplayer_sources(xplayer_sources):
            if src.url.suffix == ".m3u8":
                hls_sources.append(src)
            elif allow_mp4:
                mp4_sources.append(src)

    video_id = video.get("idHashSlug") or video.get("videoIdHashSlug") or video_id
    assert video_id
    return Video(
        id=video_id,
        title=video["title"],
        created=video.get("created") or video["addTime"],
        best_hls=max(hls_sources),
        best_mp4=max(mp4_sources, default=None),
        thumb=video.get("thumbURL") or video.get("posterUrl"),
    )


def _parse_xplayer_sources(xplayer_sources: dict[str, Any]) -> Iterable[Format]:  # noqa: C901
    if not xplayer_sources:
        return

    seen_urls: set[AbsoluteHttpURL] = set()

    def parse_format(format_dict: dict[str, str], codec: str) -> Generator[Format]:
        for key in ("url",):
            url = format_dict.get(key)
            if not url:
                continue

            quality = format_dict.get("quality") or format_dict.get("label")
            if quality == "auto":
                quality = None

            url = _parse_url(url)
            if url in seen_urls:
                continue

            seen_urls.add(url)
            res = Resolution.parse(quality)
            if res == Resolution.unknown() and (multi := next((p for p in url.parts if p.startswith("multi=")), None)):
                best = next(reversed(multi.split(",")))
                res = Resolution.parse(best.partition(":")[0])

            yield Format(res, Codec[codec.upper()], url)

    standard_sources: dict[str, list[dict[str, Any]]] = xplayer_sources.get("standard", {})
    for codec, formats_list in standard_sources.items():
        for format_dict in formats_list:
            yield from parse_format(format_dict, codec)

    hls_sources: dict[str, dict[str, str]] = xplayer_sources.get("hls", {})
    for codec, format_dict in hls_sources.items():
        yield from parse_format(format_dict, codec)


def _ensure_signed_32int(int32: int) -> int:
    unsigned_32_bit = int32 & 0xFFFFFFFF
    if unsigned_32_bit >= 0x80000000:
        return unsigned_32_bit - 0x100000000
    return unsigned_32_bit


def _make_decoder(algo: int, seed: int) -> Callable[[], int]:  # noqa: C901, PLR0915
    current_step = seed
    if algo == 1:

        def decode_next() -> int:
            nonlocal current_step
            current_step = _ensure_signed_32int(current_step * 1664525) + 1013904223
            return current_step & 255

    elif algo == 2:

        def decode_next() -> int:
            nonlocal current_step

            current_step &= 0xFFFFFFFF
            current_step ^= (current_step << 13) & 0xFFFFFFFF
            current_step ^= (current_step >> 17) & 0xFFFFFFFF
            current_step ^= (current_step << 5) & 0xFFFFFFFF
            current_step = _ensure_signed_32int(current_step)

            return current_step & 255

    elif algo == 3:

        def decode_next() -> int:
            nonlocal current_step
            val = current_step = (current_step + 2654435769) & 0xFFFFFFFF
            val ^= val >> 16
            val = (val * 2246822519) & 0xFFFFFFFF
            val ^= val >> 13
            val = (val * 3266489917) & 0xFFFFFFFF
            val ^= val >> 16

            return val & 255

    elif algo == 4:

        def decode_next() -> int:
            nonlocal current_step
            val = current_step = _ensure_signed_32int(current_step + 0x6D2B79F5)
            val = _ensure_signed_32int((val << 7) | ((val & 0xFFFFFFFF) >> 25))
            val = _ensure_signed_32int(val + 0x9E3779B9)
            val = _ensure_signed_32int(val ^ ((val & 0xFFFFFFFF) >> 11))
            val = _ensure_signed_32int(val * 0x27D4EB2D)
            return 255 & val

    elif algo == 5:

        def decode_next() -> int:
            nonlocal current_step

            current_step = _ensure_signed_32int(current_step ^ (current_step << 7))
            current_step = _ensure_signed_32int(current_step ^ ((current_step & 0xFFFFFFFF) >> 9))
            current_step = _ensure_signed_32int(current_step ^ (current_step << 8))
            current_step = _ensure_signed_32int(current_step + 0xA5A5A5A5)
            return current_step

    elif algo == 6:

        def decode_next() -> int:
            nonlocal current_step

            val = current_step * _ensure_signed_32int(0x2C9277B5)
            current_step = _ensure_signed_32int(val + _ensure_signed_32int(0xAC564B05))
            val = _ensure_signed_32int(current_step ^ ((current_step & 0xFFFFFFFF) >> 18))
            shift = (current_step & 0xFFFFFFFF) >> 27 & 31
            return _ensure_signed_32int((val & 0xFFFFFFFF) >> shift)

    elif algo == 7:

        def decode_next() -> int:
            nonlocal current_step

            current_step = _ensure_signed_32int(current_step + _ensure_signed_32int(0x9E3779B9))
            val = _ensure_signed_32int(current_step ^ (current_step << 5))
            val = _ensure_signed_32int(val * _ensure_signed_32int(0x7FEB352D))
            val = _ensure_signed_32int(val ^ ((val & 0xFFFFFFFF) >> 15))
            return _ensure_signed_32int(val * _ensure_signed_32int(0x846CA68B))

    else:
        raise ValueError(f"Unknown crypto algo: {algo}")

    return decode_next


def _is_hex(hex_string: str) -> bool:
    try:
        int(hex_string, 16)
    except ValueError:
        return False
    else:
        return True


def _decode_hex_url(encrypted_url: str) -> str:
    array = bytearray.fromhex(encrypted_url)
    algo = array[0]
    seed = _ensure_signed_32int(array[1] | (array[2] << 8) | (array[3] << 16) | (array[4] << 24))
    try:
        decode_next = _make_decoder(algo, seed)
    except ValueError:
        raise ValueError(f"Unknown encrypted URL {encrypted_url} with {algo = } and {seed = }") from None
    decoded_array = bytearray([(array[idx + 5] ^ decode_next()) & 255 for idx in range(len(array) - 5)])
    return decoded_array.decode("utf-8")
