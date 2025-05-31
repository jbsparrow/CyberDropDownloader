from __future__ import annotations

import json
import re
import struct
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple, Required, TypedDict

from Crypto.Util.Padding import pad as pad_bytes

from cyberdrop_dl.crawlers import Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.types import AbsoluteHttpURL, SupportedPaths
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


ALLOW_AVIF = False
GALLERY_PARTS = "cg", "doujinshi", "galleries", "gamecg", "imageset", "manga", "reader"
COLLECTION_PARTS = "artist", "character", "group", "series", "tag", "type"
CONTENT_HOST = "gold-usergeneratedcontent.net"
LTN_SERVER = AbsoluteHttpURL(f"https://ltn.{CONTENT_HOST}/")
PRIMARY_URL = AbsoluteHttpURL("https://hitomi.la/")
SERVERS_EXPIRE_AFTER = timedelta(minutes=40)


class SearchArguments(NamedTuple):
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
    blocked: Required[bool]
    id: Required[str]
    title: Required[str]
    files: Required[list[Image]]
    galleryurl: Required[str]
    type: Required[str]
    date: Required[str]
    datepublished: str

    # TODO: Support videos
    video: str | None
    language_localname: str
    videofilename: str | None
    language: str
    japanese_title: str
    language_url: str


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
        self.headers = {"Referer": str(PRIMARY_URL)}
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
    async def search(self, scrape_item: ScrapeItem) -> None:
        search_query = scrape_item.url.query_string
        scrape_item.setup_as_profile(self.create_title(f"{search_query} [search]"))
        gallery_sets = [gallery_set async for gallery_set in self.get_gallery_ids_from_query(search_query)]
        if not gallery_sets:
            raise ScrapeError(204)

        for gallery_id in sorted(set.intersection(*gallery_sets), reverse=True):
            new_scrape_item = scrape_item.create_child(PRIMARY_URL / f"galleries/{gallery_id}.html")
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    async def get_gallery_ids_from_query(self, search_query: str) -> AsyncGenerator[set[int]]:
        # https://ltn.gold-usergeneratedcontent.net/search.js
        # This is partial implementation. Only parses tagged words, ex `female:dark_skin`
        # Free form query searches are ignored
        for nozomi_search_args in (parse_query_word(word) for word in search_query.split(" ") if ":" in word):
            async with self.request_limiter:
                response, _ = await self.client._get(self.DOMAIN, nozomi_search_args.url, self.headers)
            yield set(decode_nozomi_response(await response.read()))

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
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name.split("-")[-1].removesuffix(".html")
        gallery = await self.get_gallery(gallery_id)
        if gallery["blocked"]:
            raise ScrapeError(403)

        title = self.create_title(f"{gallery['title']} [{gallery['type']}]", gallery["id"])
        scrape_item.setup_as_album(title, album_id=gallery["id"])
        scrape_item.possible_datetime = self.parse_date(gallery.get("datepublished") or gallery["date"])
        await self.process_gallery(scrape_item, gallery)

    async def get_gallery(self, gallery_id: str) -> Gallery:
        gallery_url = LTN_SERVER / "galleries" / gallery_id
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
            js_text = await self.client.get_text(self.DOMAIN, LTN_SERVER / "gg.js")

        root, num, default_num = [
            match_int_or_none(pattern, js_text) for pattern in (_REGEX.ROOT, _REGEX.NUM, _REGEX.DEFAULT_NUM)
        ]
        assert root is not None
        assert num is not None
        servers = Servers(root, default_num)

        for case in (match.group(1) for match in re.finditer(_REGEX.CASES, js_text)):
            servers[int(case)] = num + 1

        return servers

    async def process_gallery(self, scrape_item: ScrapeItem, gallery: Gallery) -> None:
        servers = await self.get_servers()
        gallery_reader_url = PRIMARY_URL / f"reader/{gallery['id']}.html"

        for index, image in enumerate(gallery["files"], 1):
            link = get_image_url(servers, image)
            img_reader_url = gallery_reader_url.with_fragment(str(index))
            new_scrape_item = scrape_item.create_child(img_reader_url)
            filename, ext = self.get_filename_and_ext(image["name"])
            custom_filename = Path(filename).with_suffix(link.suffix).as_posix()
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
    server_num = servers[server_hex_num]
    origin = AbsoluteHttpURL(f"https://{ext[0]}{server_num}.{CONTENT_HOST}")
    path = f"{servers.root}/{server_hex_num}/{image_hash}{ext}"
    if dir in ("webp", "avif"):
        return origin / path
    return origin / dir / path


def match_int_or_none(pattern: str, string: str) -> int | None:
    if match := re.search(pattern, string):
        return int(match.group(1).removesuffix("/"))


def decode_nozomi_response(data: bytes) -> list[int]:
    padded_bytes = pad_bytes(data, 4)
    return sorted(struct.unpack(f">{(len(padded_bytes) / 4):.0f}I", padded_bytes), reverse=True)


def parse_query_word(query_word: str) -> SearchArguments:
    left_side, _, right_side = query_word.replace("_", " ").partition(":")
    if left_side == "language":
        return SearchArguments(None, "index", right_side)
    if left_side in ("female", "male"):
        return SearchArguments("tag", query_word)
    return SearchArguments(left_side, right_side)
