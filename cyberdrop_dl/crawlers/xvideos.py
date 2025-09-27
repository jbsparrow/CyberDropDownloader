from __future__ import annotations

import asyncio
import itertools
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_text_between

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


_ACCOUNTS = ("amateurs", "profiles", "channels", "pornstars")
_EXTENDED_ACCOUNTS = tuple(
    itertools.chain.from_iterable(
        (account, singular := account.removesuffix("s"), f"{singular}-channels") for account in _ACCOUNTS
    )
)


def _escape(strings: list[str]) -> str:
    return r"\|".join(strings)


_ACCOUNT_PATHS = (f"/{_escape(sorted(_EXTENDED_ACCOUNTS))}/<name>", "/<channel_name>")


class Selectors:
    ACCOUNT_INFO_JS = "script:-soup-contains('\"id_user\":')"
    HLS_VIDEO_JS = "script:-soup-contains('setVideoHLS(')"
    DELETED_VIDEO = "h1.inlineError"
    GALLERY_IMG = "div[id*='galpic'] a.embed-responsive-item"
    GALLERY_TITLE = "h4.bg-title"
    NEXT_PAGE = "a[href]:-soup-contains('Next')"


class XVideosCrawler(Crawler):
    SUPPORTED_DOMAINS = (
        "xvideos.com",
        "xvideos.es",
        "xvideos-india.com",
        "xv-ru.com",
        "xvideos-ar.com",
    )
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Video": (
            "/video<id>/<title>",
            "/video.<encoded_id>/<title>",
            f"/{_escape(sorted(_EXTENDED_ACCOUNTS))}#quickies/({_escape(['a', 'h', 'v'])})/<video_id>",
        ),
        "Account": _ACCOUNT_PATHS,
        "Account Videos": tuple(f"{path}#_tabVideos" for path in _ACCOUNT_PATHS),
        "Account Photos": (
            *(f"{path}#_tabPhotos" for path in _ACCOUNT_PATHS),
            *(f"{path}/photos/..." for path in _ACCOUNT_PATHS),
        ),
        "Account Quickies": tuple(f"{path}#quickies" for path in _ACCOUNT_PATHS),
    }

    PRIMARY_URL = AbsoluteHttpURL("https://www.xvideos.com")
    DOMAIN = "xvideos"
    FOLDER_DOMAIN = "xVideos"
    NEXT_PAGE_SELECTOR = Selectors.NEXT_PAGE

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        if url.host.count(".") == 1:
            url = url.with_host(f"www.{url.host}")

        if url.fragment.startswith("quickies/"):
            match url.fragment.removeprefix("quickies/").split("/"):
                case ["a" | "h" | "v", video_id]:
                    return url.origin() / f"video{'' if video_id.isdecimal() else '.'}{video_id}" / "_"

        return url

    def __post_init__(self) -> None:
        self._headers = {"Accept-Language": "en-gb"}
        self._domain_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._seen_domains: set[str] = set()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if ".red" not in scrape_item.url.host:
            match scrape_item.url.parts[1:]:
                case [part, _] if part.startswith("video"):
                    return await self.video(scrape_item)
                case [_ as part, _] if part in _EXTENDED_ACCOUNTS:
                    return await self.account(scrape_item)
                case [_ as part, _, "photos" | "post", gallery_id, *_] if part in _EXTENDED_ACCOUNTS:
                    return await self.gallery(scrape_item, gallery_id)
                case [_ as part] if part not in _EXTENDED_ACCOUNTS:  # channel
                    return await self.account(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id = scrape_item.url.parts[1].removeprefix("video").removeprefix(".")
        if video_id.isdecimal() or scrape_item.url.name == "_":
            scrape_item.url = await self._get_redirect_url(scrape_item.url)
            encoded_id = scrape_item.url.parts[1].removeprefix("video.")
        else:
            encoded_id = video_id

        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self._get_soup(scrape_item.url)
        if error := soup.select_one(Selectors.DELETED_VIDEO):
            raise ScrapeError(404, css.get_text(error))

        title = css.page_title(soup, self.DOMAIN)
        scrape_item.possible_datetime = self.parse_iso_date(css.get_json_ld_date(soup))
        script = css.select_one_get_text(soup, Selectors.HLS_VIDEO_JS)
        m3u8_url = self.parse_url(get_text_between(script, "setVideoHLS('", "')"))
        m3u8, info = await self.get_m3u8_from_playlist_url(m3u8_url)
        custom_filename = self.create_custom_filename(title, ".mp4", file_id=encoded_id, resolution=info.resolution)
        # Remove url slug to prevent duplicates in database. It's language specific and not required.
        url = scrape_item.url.with_name("_")
        await self.handle_file(url, scrape_item, encoded_id + ".mp4", m3u8=m3u8, custom_filename=custom_filename)

    @error_handling_wrapper
    async def account(self, scrape_item: ScrapeItem) -> None:
        name = scrape_item.url.name
        if len(scrape_item.url.parts) > 2 and scrape_item.url.parts[1] not in _ACCOUNTS:
            scrape_item.url = await self._get_redirect_url(scrape_item.url)

        soup = await self._get_soup(scrape_item.url)
        script = css.select_one_get_text(soup, Selectors.ACCOUNT_INFO_JS)
        display_name = get_text_between(script, '"display":"', '",')
        scrape_item.setup_as_profile(self.create_title(f"{display_name} [{name}]"))

        frag = scrape_item.url.fragment
        part = "photos" if "profiles" in scrape_item.url.parts else "post"
        if not frag or "_tabPhotos" in frag:
            galleries: dict[str, Any] | list[str] = json.loads(
                get_text_between(script, '"galleries":', '"visitor":').removesuffix(",")
            )

            if isinstance(galleries, dict):
                _ = galleries.pop("0", None)

            for gallery_id in galleries:
                url = scrape_item.url / part / gallery_id.removeprefix("f-")
                new_scrape_item = scrape_item.create_child(url, new_title_part="photos")
                self.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

        if not frag or "_tabVideos" in frag:
            await self._iter_api_pages(scrape_item, scrape_item.url / "videos/new", "videos")

        if not frag or "quickies" in frag:
            has_quickies = get_text_between(script, '"has_quickies":', ",").strip()
            if has_quickies == "false":
                return

            user_id = get_text_between(script, '"id_user":', ",").strip()
            quickies_api = scrape_item.url.origin() / "quickies-api/profilevideos/all/none/N" / user_id
            await self._iter_api_pages(scrape_item, quickies_api, "quickies")

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, album_id: str) -> None:
        title: str = ""
        results = await self.get_album_results(album_id)
        async for soup in self.web_pager(scrape_item.url, relative_to=scrape_item.url.origin()):
            if not title:
                title_tag = css.select_one(soup, Selectors.GALLERY_TITLE)
                for tag in title_tag.select("*"):
                    tag.decompose()
                title = self.create_title(css.get_text(title_tag).split(">", 1)[-1].strip(), album_id)
                scrape_item.setup_as_album(title, album_id=album_id)

            for _, src in self.iter_tags(soup, Selectors.GALLERY_IMG, results=results):
                self.create_task(self.direct_file(scrape_item, src))

    async def _get_soup(self, url: AbsoluteHttpURL) -> BeautifulSoup:
        if url.host not in self._seen_domains:
            async with self._domain_locks[url.host]:
                if url.host not in self._seen_domains:
                    await self._disable_auto_translated_titles(url.origin())
                    self._seen_domains.add(url.host)

        return await self.request_soup(url, headers=self._headers)

    async def _disable_auto_translated_titles(self, origin: AbsoluteHttpURL) -> None:
        async with self.request(origin / "change-language/en", headers=self._headers):
            pass

        json_resp: dict[str, Any] = await self.request_json(
            origin / "account/feature-disabled",
            method="POST",
            headers=self._headers,
            data={"featureid": "at"},
        )
        if json_resp["code"] != 0:
            self.disabled = True
            raise ScrapeError(json_resp["code"])

    async def _iter_api_pages(self, scrape_item: ScrapeItem, api_url: AbsoluteHttpURL, new_part: str) -> None:
        per_page: int = 36
        for page in itertools.count(0):
            json_resp: dict[str, Any] = await self.request_json(
                api_url / str(page),
                method="POST",
                headers=self._headers,
            )

            if json_resp["code"] != 0:
                raise ScrapeError(json_resp["code"])

            per_page = json_resp.get("nb_per_page") or per_page
            videos: list[dict[str, str]] = json_resp["videos"]
            for video in videos:
                if new_part == "videos":
                    slug = video["u"].rpartition("/")[-1]
                    url = scrape_item.url.origin() / f"video.{video['eid']}" / slug
                else:
                    url = self.parse_url(video["url"], scrape_item.url.origin())
                new_scrape_item = scrape_item.create_child(url, new_title_part=new_part)
                self.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

            if json_resp.get("hasMoreVideos", None) is False or len(videos) < per_page:
                break
