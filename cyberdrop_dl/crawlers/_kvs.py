"""Kernel Video Sharing, a CMS for tube sites (https://www.kernel-video-sharing.com)

KVS sites look like this: https://www.kvs-demo.com

# TODO: reseach about competitor CMS listed in KVS site:

Adult Video Script (AVS)
Adult Script Pro (ASP)
Adult Watch Script
Clipshare
Data Life Engine (DLE)
Mechbunny
PHP Vibe
Predator CMS
Sharemixer
Smart Plugs
Smart Tube Pro (STP)
Tube Ace
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import re
import time
from typing import TYPE_CHECKING, Any, ClassVar, Literal, final, overload

from aiolimiter import AsyncLimiter

from cyberdrop_dl.compat import StrEnum
from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between, remove_trailing_slash

if TYPE_CHECKING:
    from collections.abc import Sequence

    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class ColletionType(StrEnum):
    categories = "category"
    tags = "tag"


@dataclasses.dataclass(slots=True)
class Video:
    id: str
    resolution: int
    url: AbsoluteHttpURL
    title: str


# KVS supports custom themes that can do basically anything to the style of the page.
# therefore these selectors may not work on some sites
class Selectors:
    ALBUM_ID = "script:contains('album_id')"
    ALBUM_NAME = "div.headline > h1"
    ALBUM_PICTURES = "div.album-list a"

    DATE_SUBMITTED = "span:contains('Submitted:')"
    DATE_ADDED = "span:contains('Added:') + span"
    DATE = f"{DATE_SUBMITTED}, {DATE_ADDED}"

    FLASHVARS = "script:contains('var flashvars')"
    KT_PLAYER = "script[src*='/kt_player.js?v=']"
    LAST_PAGE = "div.pagination-holder li.page"

    PICTURE = "div.photo-holder > img"
    PRIVATE_ALBUM = "div:contains('This album is a private album')"
    PRIVATE_VIDEO = "div:contains('This video is a private video')"
    USER_NAME = "div.headline > h2"

    VIDEO_THUMBS = "div.video-list a.thumb"


_SELECTORS = Selectors()
_PARSE_FLASHVARS_REGEX = re.compile(r"(\w+):\s*'([^']*)'")


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class KvsBlockIds:
    category: str = "list_videos_common_videos_list"
    tag: str = "list_videos_common_videos_list"
    search: str = "list_videos_videos"
    user_videos: str = "list_videos_uploaded_videos"
    user_albums: str = "list_albums_created_albums"
    playlists: str = "playlist_view_playlist_view_dev"


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class KvsVarFrom:
    category: str = "from"
    tag: str = "from"
    search: str = "from"
    user_videos: str = "from_uploaded_videos"
    user_albums: str = "list_albums"
    playlists: str = "UNKNOWN"


pornrex = "list_videos_common_videos_list_norm"


class KernelVideoSharingCrawler(Crawler, is_abc=True):
    SUPPORTED_PATHS: ClassVar[dict[str, str | tuple[str, ...]]] = {
        "Album": (
            "/(albums|album|gallery)/<album_name>/",
            "/(albums|album|gallery)/<album_name>/",
        ),
        "Image": "/(albums|album|gallery)/<album_name>/<image_name>/",
        "Search": (
            "/search/?q=<search_query>",
            "/search/<search_query>/",
        ),
        "Category": "/categories/<category>/",
        "Tag": "/tags/<tag>/",
        "Video": (
            "/(videos|video)/<video_name>/",
            "/(videos|video)/<video_id>/<video_name>/",
        ),
        "Member": "/members/<member>/",
        "Model": "/models/<model>/",
        "Playlist": "/playlists/<playlist>/",
    }

    # BASIC supports: videos, categories, tags and playlists
    # ADVANCED supports: everything in BASIC + models and members
    # ULTIMATE supports: everything in ADVANCED + albums (photos)
    #
    # This attribute is only used for the auto generated supported paths on the wiki
    # At runtime CDL will try to parse and download from any URL assuming the site has an ULTIMATE license
    # https://www.kernel-video-sharing.com/en/order/
    KVS_PACKAGE_LICENSE: Literal["BASIC", "ADVANCED", "ULTIMATE"] = "ULTIMATE"
    KVS_BLOCK_IDS: ClassVar = KvsBlockIds()
    KVS_VAR_FROMS: ClassVar = KvsVarFrom()
    DEFAULT_TRIM_URLS: ClassVar = False

    def __init_subclass__(cls, **kwargs):
        assert cls.KVS_PACKAGE_LICENSE in ("BASIC", "ADVANCED", "ULTIMATE"), "invalid kvs license"
        if cls.KVS_PACKAGE_LICENSE != "ULTIMATE":
            paths = cls.SUPPORTED_PATHS.copy()
            _ = paths.pop("Album", None), paths.pop("Image", None)
            if cls.KVS_PACKAGE_LICENSE != "ADVANCED":
                _ = paths.pop("Model", None), paths.pop("Member", None)
            cls.SUPPORTED_PATHS = paths  # type: ignore[reportIncompatibleVariableOverride]
        cls.KVS_ITEM_SELECTOR = ", ".join(
            (
                _SELECTORS.VIDEO_THUMBS,
                f"div#{cls.KVS_BLOCK_IDS.tag} a",
                f"div#{cls.KVS_BLOCK_IDS.category} a",
                _SELECTORS.ALBUM_PICTURES,
            ),
        )
        super().__init_subclass__(**kwargs)

    def __post_init__(self) -> None:
        self.request_limiter = AsyncLimiter(3, 10)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        # KVS allows webmasters to override URL paths. Subclasses may need to implement a custom fetch to handle different paths
        # https://forum.kernel-video-sharing.com/topic/6684-no-links-on-my-website-are-working/

        # TODO: make sure the scrape mapper does not trim URLs
        clean_url = remove_trailing_slash(scrape_item.url)
        match clean_url.parts[1:]:
            case ["categories" | "tags" as type_, slug] if type_ in ColletionType:
                return await self.collection(scrape_item, slug, ColletionType(type_))
            case ["members", _]:
                return await self.profile(scrape_item)
            case ["videos" | "video", _, *_]:
                return await self.video(scrape_item)
            case ["albums" | "album" | "gallery", _]:
                return await self.album(scrape_item)
            case ["albums" | "album" | "gallery", _, _]:
                return await self.picture(scrape_item)
            case ["search", query]:
                return await self.search(scrape_item, query)
            case ["search"] if query := scrape_item.url.query.get("q"):
                return await self.search(scrape_item, query)
            case ["playlists", *_]:
                # TODO: Add playlist support
                raise ValueError
            case _:
                raise ValueError

    @final
    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, search_query: str) -> None:
        title = self.create_title(f"{search_query} [search]")
        scrape_item.setup_as_album(title)
        await self._iter_pages(
            scrape_item, self.KVS_BLOCK_IDS.search, self.KVS_VAR_FROMS.search, search_query=search_query
        )

    @final
    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, slug: str, collection_type: ColletionType) -> None:
        if collection_type is ColletionType.tags:
            block_id = self.KVS_BLOCK_IDS.tag
            var_from = self.KVS_VAR_FROMS.tag
        else:
            block_id = self.KVS_BLOCK_IDS.category
            var_from = self.KVS_VAR_FROMS.category

        title = self.create_title(f"{slug} [{collection_type}]")
        scrape_item.setup_as_album(title)
        await self._iter_pages(scrape_item, block_id, var_from)

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        soup = await self._get_soup(scrape_item.url)
        user_name = css.select_one_get_text(soup, _SELECTORS.USER_NAME).split("'s Profile")[0].strip()
        title = self.create_title(f"{user_name} [user]")
        scrape_item.setup_as_profile(title)

        def new_item(new_part: str):
            url = (remove_trailing_slash(scrape_item.url) / new_part / "").with_query(scrape_item.url.query)
            return scrape_item.create_child(url, new_title_part=new_part)

        await self._iter_pages(new_item("videos"), self.KVS_BLOCK_IDS.user_videos, self.KVS_VAR_FROMS.user_videos)
        await self._iter_pages(new_item("albums"), self.KVS_BLOCK_IDS.user_albums, self.KVS_VAR_FROMS.user_albums)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self._get_soup(scrape_item.url)
        video = self.get_embeded_video(soup)
        filename, ext = self.get_filename_and_ext(video.url.name or video.url.parent.name)
        custom_filename = self.create_custom_filename(video.title, ext, file_id=video.id, resolution=video.resolution)
        scrape_item.possible_datetime = self._get_video_date(soup)
        await self.handle_file(
            scrape_item.url, scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=video.url
        )

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        soup = await self._get_soup(scrape_item.url)
        if soup.select_one(_SELECTORS.PRIVATE_ALBUM):
            raise ScrapeError(401, "Private album")

        album_id = _get_album_id(soup)
        results = await self.get_album_results(album_id)
        title = css.select_one_get_text(soup, _SELECTORS.ALBUM_NAME)
        title = self.create_title(f"{title} [album]", album_id)
        scrape_item.setup_as_album(title, album_id=album_id)
        await self._iter_album_pages(scrape_item, soup, results)

    @error_handling_wrapper
    async def picture(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        soup = await self._get_soup(scrape_item.url)
        url = self.parse_url(css.select_one_get_attr(soup, _SELECTORS.PICTURE, "src"))
        if iso_date := get_json_ld_value(soup, "uploadDate", strict=False):
            scrape_item.possible_datetime = self.parse_iso_date(iso_date)
        if not scrape_item.album_id:
            scrape_item.album_id = _get_album_id(soup)
        filename, ext = self.get_filename_and_ext(url.name or url.parent.name)
        await self.handle_file(url, scrape_item, filename, ext)

    @classmethod
    def get_embeded_video(cls, soup: BeautifulSoup) -> Video:
        if soup.select_one(_SELECTORS.PRIVATE_VIDEO):
            raise ScrapeError(401, "Private video")

        script = css.select_one_get_text(soup, _SELECTORS.FLASHVARS)
        flashvars = get_text_between(script, "var flashvars =", ";")
        video = _parse_flashvars(flashvars)
        if not video.title:
            title = open_graph.get_title(soup) or css.select_one_get_text(soup, "title")
            title = sanitize_page_title(title, cls.DOMAIN)
            assert title
            video.title = title
        return video

    async def _get_soup(self, url: AbsoluteHttpURL):
        async with self.request_limiter:
            return await self.client.get_soup(self.DOMAIN, url)

    async def _iter_album_pages(self, scrape_item: ScrapeItem, soup: BeautifulSoup, results: dict[str, int]) -> None:
        # This does not work on every site. Most subclasses will need to override this
        # 1. some themes have all image src available on the main album page
        # 2. some themes only have thumbnails available, so we need to make a new request
        # 3. some themes have pagination enabled

        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_PICTURES, results=results):
            self.create_task(self.run(new_scrape_item))

    async def _iter_pages(
        self,
        scrape_item: ScrapeItem,
        block_id: str,
        var_from: str,
        *,
        search_query: str | None = None,
    ) -> None:
        soup = await self._get_soup(scrape_item.url)
        try:
            last_page = int(css.get_text(soup.select(_SELECTORS.LAST_PAGE)[-1]))
        except css.SelectorError:
            last_page = 1
        for _, new_scrape_item in self.iter_children(scrape_item, soup, self.KVS_ITEM_SELECTOR):
            self.create_task(self.run(new_scrape_item))

        if last_page > 1:
            # The default KVS theme does not support pages in the URL path, that means no pagination support
            # We need to load additional pages simulating an AJAX request to make sure we can handle all sites
            await self._iter_additional_pages(scrape_item, block_id, var_from, search_query, last_page)

    @final
    async def _iter_additional_pages(
        self,
        scrape_item: ScrapeItem,
        block_id: str,
        var_from: str,
        search_query: str | None,
        last_page: int,
    ) -> None:
        # https://forum.kernel-video-sharing.com/topic/346-how-to-enable-pagination-in-related-videos/
        # TODO: This canonical URL may not be needed anymore
        canonical_url = scrape_item.url.with_path("/".join(scrape_item.url.parts[1:3])) / ""
        ajax_url = canonical_url.with_query(
            mode="async",
            function="get_block",
            block_id=block_id,
            is_private="0,1",  # TODO: Do not request private videos if user is not logged in (No PHP session cookies)
            q=search_query or "",
            sort_by=scrape_item.url.query.get("sort_by") or "post_date",
        )

        for page in itertools.count(2):
            if page > last_page:
                break
            soup = await self._get_soup(ajax_url.update_query({var_from: page, "_": int(time.time() * 1000)}))
            for _, new_scrape_item in self.iter_children(scrape_item, soup, self.KVS_ITEM_SELECTOR):
                self.create_task(self.run(new_scrape_item))

    def _get_video_date(self, soup: BeautifulSoup) -> int | None:
        # older themes do no have json_ld or open_graph props
        if iso_date := (
            get_json_ld_value(soup, "uploadDate", strict=False) or open_graph.get("video:release_date", soup)
        ):
            return self.parse_iso_date(iso_date)
        if date_row := soup.select_one(_SELECTORS.DATE):
            human_date = css.get_text(date_row).split(":", 1)[-1].strip()
            return self.parse_date(human_date)


# TODO: Move title funtions to css utils
def sanitize_page_title(title: str, domain: str) -> str:
    sld = domain.rpartition(".")[0]

    def clean(title: str, char: str):
        front, _, tail = title.rpartition(char)
        if sld in tail.casefold():
            title = front.strip()
        return title

    return clean(clean(title, "|"), " - ")


def page_title(soup: BeautifulSoup, domain: str | None = None) -> str:
    title = css.select_one_get_text(soup, "title")
    if domain:
        return sanitize_page_title(title, domain)
    return title


# TODO: Move json_ld funtions to css utils
@overload
def get_json_ld(soup: BeautifulSoup, /, contains: str | None, *, strict: Literal[True] = True) -> dict[str, Any]: ...


@overload
def get_json_ld(soup: BeautifulSoup, /, contains: str | None, *, strict: Literal[False]) -> dict[str, Any] | None: ...


def get_json_ld(soup: BeautifulSoup, /, contains: str | None, *, strict: bool = True) -> dict[str, Any] | None:
    selector = "script[type='application/ld+json']"
    if contains:
        selector += f":contains('{contains}')"
    try:
        ld_json = json.loads(css.select_one_get_text(soup, selector))
    except css.SelectorError:
        if not strict:
            return
        raise
    return ld_json


def get_json_ld_value(soup: BeautifulSoup, key: str, *, strict: bool = True) -> Any:
    if ld_json := get_json_ld(soup, key, strict=strict):
        return ld_json[key]


def _get_album_id(soup: BeautifulSoup) -> str:
    js_text = css.select_one_get_text(soup, _SELECTORS.ALBUM_ID)
    return get_text_between(js_text, "params['album_id'] =", ";").partition(",")[0].strip()


def _get_player_version(soup: BeautifulSoup) -> tuple[int, ...] | None:
    if player_url := css.select_one_get_attr(soup, _SELECTORS.KT_PLAYER, "src"):
        version_str = AbsoluteHttpURL(player_url).query["v"]
        return tuple(map(int, version_str.split(".")))


# TODO: Move this funtion to the generic crawler
# TODO: Make the generic crawler create new crawlers on command
def has_embeded_kvs_video(soup: BeautifulSoup) -> bool:
    return bool(_get_player_version(soup))


# URL de-obfuscation code for kvs, adapted from yt-dlp
# https://github.com/yt-dlp/yt-dlp/blob/e1847535e28788414a25546a45bebcada2f34558/yt_dlp/extractor/generic.py#L2279


_HASH_LENGTH = 32
_VIDEO_URL_KEYS = re.compile(r"^video_(?:url|alt_url\d*)$")


def _parse_flashvars(flashvars_text: str) -> Video:
    flashvars: dict[str, str] = dict(_PARSE_FLASHVARS_REGEX.findall(flashvars_text))
    url_keys = filter(_VIDEO_URL_KEYS.match, flashvars.keys())
    license_token = _get_license_token(flashvars["license_code"])

    def get_formats():
        for key in url_keys:
            url_str = flashvars[key]
            if "/get_file/" not in url_str:
                continue
            resolution = int(flashvars[f"{key}_text"].removesuffix("p"))
            url = _deobfuscate_url(url_str, license_token)
            yield resolution, url

    resolution, url = max(get_formats())
    return Video(flashvars["video_id"], resolution, url, flashvars["video_title"])


def _deobfuscate_url(video_url_str: str, license_token: Sequence[int]) -> AbsoluteHttpURL:
    raw_url_str = video_url_str.removeprefix("function/0/")
    url = AbsoluteHttpURL(raw_url_str)
    is_obfuscated = raw_url_str != video_url_str
    if not is_obfuscated:
        return url

    hash, tail = url.parts[3][:_HASH_LENGTH], url.parts[3][_HASH_LENGTH:]
    indices = list(range(_HASH_LENGTH))

    # Swap indices of hash according to the destination calculated from the license token
    accum = 0
    for src in reversed(range(_HASH_LENGTH)):
        accum += license_token[src]
        dest = (src + accum) % _HASH_LENGTH
        indices[src], indices[dest] = indices[dest], indices[src]

    new_parts = list(url.parts)
    new_parts[3] = "".join(hash[index] for index in indices) + tail
    return url.with_path("/".join(new_parts[1:]), keep_query=True, keep_fragment=True)


def _get_license_token(license_code: str) -> tuple[int, ...]:
    license_code = license_code.removeprefix("$")
    license_values = [int(char) for char in license_code]
    modlicense = license_code.replace("0", "1")
    middle = len(modlicense) // 2
    fronthalf = int(modlicense[: middle + 1])
    backhalf = int(modlicense[middle:])
    modlicense = str(4 * abs(fronthalf - backhalf))[: middle + 1]

    return tuple(
        (license_values[index + offset] + current) % 10
        for index, current in enumerate(map(int, modlicense))
        for offset in range(4)
    )
