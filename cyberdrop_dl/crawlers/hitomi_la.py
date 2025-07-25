from __future__ import annotations

import asyncio
import json
import re
import struct
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar, NamedTuple, Required, TypedDict

from aiolimiter import AsyncLimiter

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


ALLOW_AVIF = False
GALLERY_PARTS = "cg", "doujinshi", "galleries", "gamecg", "imageset", "manga", "reader", "anime"
COLLECTION_PARTS = "artist", "character", "group", "series", "tag", "type"
CONTENT_HOST = "gold-usergeneratedcontent.net"
LTN_SERVER = AbsoluteHttpURL(f"https://ltn.{CONTENT_HOST}/")
PRIMARY_URL = AbsoluteHttpURL("https://hitomi.la")
VIDEOS_SERVER = AbsoluteHttpURL(f"https://streaming.{CONTENT_HOST}/")
SERVERS_EXPIRE_AFTER = timedelta(minutes=40)


class NozomiSearchArguments(NamedTuple):
    area: str | None
    tag: str
    language: str = "all"

    @property
    def url(self) -> AbsoluteHttpURL:
        if self.area:
            return LTN_SERVER / "n" / self.area / f"{self.tag}-{self.language}.nozomi"
        return LTN_SERVER / "n" / f"{self.tag}-{self.language}.nozomi"


class Servers(defaultdict[int, int]):
    def __init__(self, root: int, default: int | None = None) -> None:
        if default is None:
            default = 0
        super().__init__(lambda: default)
        self.root = root
        self.fetch_datetime = datetime.now()


class Regex:
    ROOT = r"b: '(.+)'"
    CASES = r"case (\d+):"
    DEFAULT_NUM = r"var o = (\d+)"
    NUM = r"o = (\d+); break;"


class Image(TypedDict, total=False):
    hash: Required[str]
    name: Required[str]
    hasavif: int


class Gallery(TypedDict, total=False):
    blocked: Required[int]
    id: Required[str]
    title: Required[str]
    files: Required[list[Image]]
    type: Required[str]
    date: Required[str]
    datepublished: str
    videofilename: str


_REGEX = Regex()


class HitomiLaCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Gallery": tuple(f"/{g}/..." for g in GALLERY_PARTS),
        "Collection": tuple(f"/{g}/..." for g in COLLECTION_PARTS),
        "Search": "/search.html?<query>",
    }
    PRIMARY_URL: ClassVar = PRIMARY_URL
    DOMAIN: ClassVar = "hitomi.la"

    def __post_init__(self) -> None:
        self._semaphore = asyncio.Semaphore(3)
        self.request_limiter = AsyncLimiter(1, 1)
        self.headers = {"Referer": str(PRIMARY_URL), "Origin": str(PRIMARY_URL)}
        self._servers: Servers | None = None

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in GALLERY_PARTS):
            return await self.gallery(scrape_item)
        if any(p in scrape_item.url.parts for p in COLLECTION_PARTS):
            return await self.collection(scrape_item)
        if scrape_item.url.name == "search.html" and scrape_item.url.query_string:
            return await self.search(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        colletion_type = scrape_item.url.parts[1]
        name, _, language = scrape_item.url.name.removesuffix(".html").partition("-")

        if name == "index":
            title = self.create_title(f"{name} [{language}]")
            nozomi_url = LTN_SERVER / f"{name}-{language}.nozomi"
        else:
            title = self.create_title(f"{name} [{colletion_type}][{language}]")
            nozomi_url = LTN_SERVER / colletion_type / f"{name}-{language}.nozomi"

        scrape_item.setup_as_profile(title)
        async with self.request_limiter:
            response, _ = await self.client._get(self.DOMAIN, nozomi_url, self.headers)

        for gallery_id in decode_nozomi_response(await response.read()):
            new_scrape_item = scrape_item.create_child(PRIMARY_URL / f"galleries/{gallery_id}.html")
            # await immediately to prevent overwhelming the downloader
            # there could be thousands of galleries in the result
            await self.run(new_scrape_item)
            scrape_item.add_children()

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_query = scrape_item.url.query_string
        scrape_item.setup_as_profile(self.create_title(f"{search_query} [search]"))
        gallery_sets = [gallery_set async for gallery_set in self.get_gallery_sets_from_query(search_query)]
        if not gallery_sets:
            raise ScrapeError(204)

        for gallery_id in sorted(set.intersection(*gallery_sets), reverse=True):
            new_scrape_item = scrape_item.create_child(PRIMARY_URL / f"galleries/{gallery_id}.html")
            await self.run(new_scrape_item)
            scrape_item.add_children()

    async def get_gallery_sets_from_query(self, search_query: str) -> AsyncGenerator[set[int]]:
        # https://ltn.gold-usergeneratedcontent.net/search.js
        # This is partial implementation. Only parses tagged words, ex `female:dark_skin`
        # Free form query searches are ignored
        for nozomi_search_args in (parse_query_word(word) for word in search_query.split(" ") if ":" in word):
            async with self.request_limiter:
                response, _ = await self.client._get(self.DOMAIN, nozomi_search_args.url, self.headers)
            yield set(decode_nozomi_response(await response.read()))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name.split("-")[-1].removesuffix(".html")
        gallery = await self.get_gallery(gallery_id)
        if gallery["blocked"]:
            raise ScrapeError(403)

        scrape_item.url = PRIMARY_URL / "galleries" / gallery_id
        title = self.create_title(f"{gallery['title']} [{gallery['type']}]", gallery["id"])
        scrape_item.setup_as_album(title, album_id=gallery["id"])
        date_str = gallery.get("datepublished") or gallery["date"]
        scrape_item.possible_datetime = self.parse_iso_date(date_str)
        await self.process_gallery(scrape_item, gallery)

    async def get_gallery(self, gallery_id: str) -> Gallery:
        gallery_url = LTN_SERVER / f"galleries/{gallery_id}.js"
        async with self.request_limiter:
            js_text = await self.client.get_text(self.DOMAIN, gallery_url, self.headers)
        return json.loads(js_text.split("=", 1)[-1])

    async def get_servers(self) -> Servers:
        async with self.startup_lock:
            if self._servers is None or (datetime.now() - self._servers.fetch_datetime > SERVERS_EXPIRE_AFTER):
                self._servers = await self._get_servers()
        return self._servers

    async def _get_servers(self) -> Servers:
        # https://ltn.gold-usergeneratedcontent.net/gg.js
        async with self.request_limiter:
            js_text = await self.client.get_text(self.DOMAIN, LTN_SERVER / "gg.js", cache_disabled=True)

        root, num, default_num = [
            match_int_or_none(pattern, js_text) for pattern in (_REGEX.ROOT, _REGEX.NUM, _REGEX.DEFAULT_NUM)
        ]
        assert root is not None
        assert num is not None
        servers = Servers(root, default_num)

        for case in (match.group(1) for match in re.finditer(_REGEX.CASES, js_text)):
            servers[int(case)] = num

        return servers

    async def process_gallery(self, scrape_item: ScrapeItem, gallery: Gallery) -> None:
        servers = await self.get_servers()
        gallery_reader_url = PRIMARY_URL / f"reader/{gallery['id']}.html"
        results = await self.get_album_results(gallery["id"])

        if video_filename := gallery.get("videofilename"):
            link = VIDEOS_SERVER / "videos" / video_filename
            filename, ext = self.get_filename_and_ext(video_filename)
            await self.handle_file(link, scrape_item, filename, ext)

        for index, image in enumerate(gallery["files"], 1):
            img_reader_url = gallery_reader_url.with_fragment(str(index))
            if self.check_album_results(img_reader_url, results):
                continue
            link = get_image_url(servers, image)
            new_scrape_item = scrape_item.create_child(img_reader_url)
            filename, ext = self.get_filename_and_ext(image["name"])
            custom_filename = self.create_custom_filename(filename, link.suffix)
            await self.handle_file(
                img_reader_url, new_scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
            )


def get_image_url(servers: Servers, image: Image) -> AbsoluteHttpURL:
    if ALLOW_AVIF and image.get("hasavif"):
        dir = "avif"
    else:
        dir = "webp"
    return url_from_hash(servers, image, dir, ext=f".{dir}")


def url_from_hash(servers: Servers, image: Image, dir: str, ext: str | None = None) -> AbsoluteHttpURL:
    # https://ltn.gold-usergeneratedcontent.net/common.js
    if ext is None:
        _, ext = get_filename_and_ext(image["name"])

    image_hash = image["hash"]
    server_hex_num = int(image_hash[-1] + image_hash[-3:-1], base=16)
    server_num = servers[server_hex_num] + 1
    origin = AbsoluteHttpURL(f"https://{ext[1]}{server_num}.{CONTENT_HOST}")
    path = f"{servers.root}/{server_hex_num}/{image_hash}{ext}"
    if dir in ("webp", "avif"):
        return origin / path
    return origin / dir / path


def match_int_or_none(pattern: str, string: str) -> int | None:
    if match := re.search(pattern, string):
        return int(match.group(1).removesuffix("/"))


def decode_nozomi_response(data: bytes) -> tuple[int, ...]:
    return struct.unpack(f">{(len(data) / 4):.0f}I", data)


def parse_query_word(query_word: str) -> NozomiSearchArguments:
    query_word = query_word.replace("_", " ")
    left_side, _, right_side = query_word.partition(":")
    if left_side == "language":
        return NozomiSearchArguments(None, "index", right_side)
    if left_side in ("female", "male"):
        return NozomiSearchArguments("tag", query_word)
    return NozomiSearchArguments(left_side, right_side)
