from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Unpack, final, override

from aiohttp import ClientConnectorError

from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.constants import FileExt
from cyberdrop_dl.crawlers import Registry
from cyberdrop_dl.crawlers.crawler import API, Crawler, DownloadConfig, SupportedDomains, SupportedPaths
from cyberdrop_dl.exceptions import DDOSGuardError, ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, open_graph
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.clients import HttpMethod
    from cyberdrop_dl.clients.request import RequestParams
    from cyberdrop_dl.url_objects import ScrapeItem


_HOST_OPTIONS: frozenset[str] = frozenset(("bunkr.site", "bunkr.cr", "bunkr.ph"))
_find_js_vars = re.compile(r'var\s+(\w+)\s*=\s*(".*?"|\'.*?\'|[^;]+);', re.DOTALL).findall
known_bad_hosts: set[str] = set()


@final
class Selector:
    ALBUM_FILES = "script:-soup-contains('window.albumFiles = ')"
    DOWNLOAD_BTN = "a.btn.ic-download-01"
    SERVER_UNDER_MAINTENANCE = "h2:-soup-contains('Server under maintenance')"
    JS_VARS = "script:-soup-contains-own('var jsCDN')"


@HTTPConfig(rate_limit=(5, 1))
@DownloadConfig(server_lock=True)
class BunkrCrawler(Crawler):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ("bunkr",)
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/a/<album_id>",
        "Video": "/v/<slug>",
        "File": (
            "/f/<slug>",
            "/d/<slug>",
            "/i/<slug>",
        ),
        "Stream redirect": "/<slug>",
    }

    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://bunkr.cr")
    DOMAIN: ClassVar[str] = "bunkr"
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = (
        "bunkr.black",
        "bunkr.su",
        "bunkr.is",
        "bunkr.la",
        "bunkr.se",
        "bunkrr.su",
    )

    _known_good_host: ClassVar[str | None] = None

    @staticmethod
    @override
    def __db_path__(url: AbsoluteHttpURL, /) -> str:
        if "thumbs" in url.parts:
            return url.path
        return "/" + url.name

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = _fix_domain(url)
        match url.parts[1:]:
            case ["v" | "d" | "i", js_slug]:
                return url.origin() / "f" / js_slug
            case _:
                return url

    def __post_init__(self) -> None:
        self.api: BunkrAPI = BunkrAPI.from_crawler(self)
        self._parse_files = _make_album_parser()
        self._redirect_lock: asyncio.Lock = asyncio.Lock()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["file", file_id] if scrape_item.url.host == self.api.DL_ENDPOINT.host:
                return await self.file_download(scrape_item, file_id)
            case ["a", album_id]:
                return await self.album(scrape_item, album_id)
            case ["v" | "d" | "i", _]:
                return await self.follow_redirect(scrape_item)
            case ["f", _]:
                return await self.file(scrape_item)
            case [_] if _is_stream_redirect(scrape_item.url.host):
                return await self.follow_redirect(scrape_item)
            case _:
                raise ValueError

    async def request_redirect(
        self, url: AbsoluteHttpURL, method: HttpMethod = "GET", **kwargs: Unpack[RequestParams]
    ) -> AbsoluteHttpURL:
        try:
            return await super().request_redirect(url, method, **kwargs)
        except (ClientConnectorError, DDOSGuardError):
            if self.is_subdomain(url):
                raise

            if not self._known_good_host:
                async with self._redirect_lock:
                    if not self._known_good_host:
                        _ = await self._request_soup_lenient(url)

            assert self._known_good_host
            return await super().request_redirect(url.with_host(self._known_good_host), method, **kwargs)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem, album_id: str) -> None:
        soup = await self._request_soup_lenient(scrape_item.url.with_query(advanced=1))
        name = open_graph.title(soup)
        title = self.create_title(name, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        origin = scrape_item.url.origin()
        for file in self._parse_files(css.select_text(soup, Selector.ALBUM_FILES)):
            web_url = origin / "f" / file.slug
            new_item = scrape_item.create_child(web_url)
            new_item.uploaded_at = self.parse_date(file.timestamp, "%H:%M:%S %d/%m/%Y")
            self.create_task(self.run(new_item, check_referer=True))
            scrape_item.add_children()

    @override
    async def check_complete_from_referer(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        referer: AbsoluteHttpURL,
        *,
        any_crawler: bool = False,
    ) -> bool:
        if not self.is_subdomain(referer):
            referer = referer.with_host(self.PRIMARY_URL.host)

        return await super().check_complete_from_referer(referer, any_crawler=any_crawler)

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self._request_soup_lenient(scrape_item.url)
        if soup.select_one(Selector.SERVER_UNDER_MAINTENANCE):
            raise ScrapeError("Bunkr Maintenance", "Server under maintenance")

        thumb = open_graph.get_image(soup)

        try:
            js_vars = _extract_js_vars(soup)
            cdn = js_vars["jsCDN"]
            thumb = js_vars.get("videoCoverUrl") or thumb
        except css.SelectorError:
            dl_url = css.select(soup, Selector.DOWNLOAD_BTN, "href")
            file_id = self.parse_url(dl_url).name
            src, filename = await self.api.download(file_id)
        else:
            filename = open_graph.title(soup)
            src = self.parse_url(cdn)

        await self._file(scrape_item, src, filename, self.parse_url(thumb) if thumb else None)

    @error_handling_wrapper
    async def file_download(self, scrape_item: ScrapeItem, file_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return
        source, name = await self.api.download(file_id)
        await self._file(scrape_item, source, name)

    async def _file(
        self,
        scrape_item: ScrapeItem,
        src: AbsoluteHttpURL,
        filename: str | None = None,
        thumbnail: AbsoluteHttpURL | None = None,
    ) -> None:
        referer = scrape_item.url
        if not self.is_subdomain(referer):
            referer = referer.with_host(self.PRIMARY_URL.host)

        if await self.check_complete(src, referer):
            return

        name = src.query.get("n") or filename or src.name
        src = src.update_query(n=name)
        filename, ext = self.get_filename_and_ext(name, assume_ext=".mp4")
        await self.handle_file(
            src,
            scrape_item,
            name,
            ext,
            custom_filename=filename,
            referer=referer,
            debrid_link=lambda: self.api.sign(src),
            thumbnail=thumbnail and _fix_thumb(thumbnail),
        )

    async def _try_request_soup(self, url: AbsoluteHttpURL) -> BeautifulSoup | None:
        try:
            async with self.request(url) as resp:
                soup = await resp.soup()

        except (ClientConnectorError, DDOSGuardError):
            known_bad_hosts.add(url.host)
            if not _HOST_OPTIONS - known_bad_hosts:
                raise
        else:
            if not self._known_good_host:
                type(self)._known_good_host = resp.url.host
            if url.query.get("advanced") and url.query != resp.url.query:
                soup = await self.request_soup(resp.url.with_query(url.query))
            return soup

    async def _request_soup_lenient(self, url: AbsoluteHttpURL) -> BeautifulSoup:
        """Request soup with re-trying logic to use multiple hosts.

        We retry with a new host until we find one that's not DNS blocked nor DDoS-Guard protected

        If we find one, keep a reference to it and use it for all future requests"""

        if self._known_good_host:
            return await self.request_soup(url.with_host(self._known_good_host))

        async with self._startup_lock:
            if url.host not in known_bad_hosts and (soup := await self._try_request_soup(url)):
                return soup

            for host in _HOST_OPTIONS - known_bad_hosts:
                if soup := await self._try_request_soup(url.with_host(host)):
                    return soup

        # everything failed, do the request with the original URL to throw an exception
        return await self.request_soup(url)


@HTTPConfig(
    headers={
        "Referer": "https://dl.bunkr.cr/",
        "Origin": "https://dl.bunkr.cr",
    }
)
class BunkrAPI(API):
    DL_ENDPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://dl.bunkr.cr/api/_001_v2")
    SIGN_ENDPOINT: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://glb-apisign.cdn.cr/sign")

    async def download(self, file_id: str) -> tuple[AbsoluteHttpURL, str | None]:
        resp = await self.request_json(self.DL_ENDPOINT, json={"id": file_id})
        url = self.parse_url(resp["mediafiles"]).with_path(resp["path"])
        return url, resp.get("original")

    async def sign(self, src: AbsoluteHttpURL) -> AbsoluteHttpURL:
        api_url = self.SIGN_ENDPOINT.with_query(path=src.path)
        resp = await self.request_json(api_url)
        return src.with_query(token=resp["token"], ex=resp["ex"])


@dataclasses.dataclass(slots=True)
class File:
    id: int
    name: str
    original: str | None
    slug: str
    type: str
    extension: str
    size: int
    timestamp: str
    thumbnail: str
    cdnEndpoint: str  # noqa: N815


def _make_album_parser() -> Callable[[str], Generator[File]]:
    translation_map = {f" {field.name}: ": f'"{field.name}": ' for field in dataclasses.fields(File)}
    pattern = re.compile("|".join(sorted(translation_map.keys(), key=len, reverse=True)))

    def translate(text: str) -> str:
        return pattern.sub(lambda m: translation_map[m.group(0)], text.replace("\\'", "'")).strip()

    def decode(content: str) -> Generator[File]:
        file: dict[str, Any]
        for file in json.loads(content):
            yield File(**file)

    def parse(album_js: str) -> Generator[File]:
        content = translate(album_js[album_js.find("=") + 1 : album_js.rfind("];")])
        return decode(content.rstrip(",") + "]")

    return parse


def _fix_thumb(thumb: AbsoluteHttpURL) -> AbsoluteHttpURL | None:
    name = Path(thumb.name)
    if len(name.suffixes) < 2:
        return thumb
    *_, file_ext, thumb_ext = name.suffixes
    if "grid" in file_ext:
        return thumb
    if file_ext.casefold() not in FileExt.MEDIA:
        return None
    return thumb.with_name(name.stem).with_suffix(thumb_ext)


def _is_stream_redirect(host: str) -> bool:
    first_subdomain = host.split(".", maxsplit=1)[0]
    prefix, _, number = first_subdomain.partition("cdn")
    if not prefix and number.isdigit():
        return True
    return any(part in host for part in ("cdn12", "cdn-")) or host == "cdn.bunkr.ru"


def _extract_js_vars(soup: BeautifulSoup) -> dict[str, str]:
    script = css.select_text(soup, Selector.JS_VARS)
    return {k: _fix_encoding(v).strip("\"'") for k, v in _find_js_vars(script)}


def _fix_encoding(val: str) -> str:
    # Double-quoted page vars are JSON strings, so decode every escape, not just `\/`
    if val.startswith('"'):
        try:
            return json.loads(val)
        except ValueError:
            pass
    return val.replace(r"\/", "/")


@Registry.database.referer_fix_for(BunkrCrawler)
def fix_db_referer(referer: str) -> str:
    url = BunkrCrawler.transform_url(AbsoluteHttpURL(referer))
    if BunkrCrawler.is_subdomain(url):
        return str(url)

    return str(url.with_host(BunkrCrawler.PRIMARY_URL.host))


def _fix_domain(url: AbsoluteHttpURL) -> AbsoluteHttpURL:
    if url.host == "get.bunkrr.su":
        return url.with_host("dl.bunkr.cr")
    if url.host in BunkrCrawler.OLD_DOMAINS:
        return url.with_host(BunkrCrawler.PRIMARY_URL.host)
    return url
