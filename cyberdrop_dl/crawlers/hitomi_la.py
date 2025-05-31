from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Required, TypedDict

from cyberdrop_dl.crawlers.crawler import Crawler
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.types import AbsoluteHttpURL
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://hitomi.la/")
GALLERY_PARTS = "cg", "doujinshi", "galleries", "gamecg", "imageset", "manga", "reader"
TAG_PARTS = "artist", "character", "group", "series", "tag", "type"

CONTENT_HOST = "gold-usergeneratedcontent.net"
LTN_SERVER = AbsoluteHttpURL(f"https://ltn.{CONTENT_HOST}/")
ALLOW_AVIF = False


class Servers(defaultdict[int, int]):
    base: int

    def __init__(self, base: int, default: int = 0, *args, **kwargs) -> None:
        super().__init__(lambda: default, *args, **kwargs)
        self.base = base


class Regex:
    BASE = r"b: '(.+)'"
    CASES = r"case (\d+):"
    DEFAULT_NUM = r"var o = (\d+)"
    NUM = r"o = (\d+); break;"


_REGEX = Regex()


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


class HitomiLaCrawler(Crawler):
    PRIMARY_URL = PRIMARY_URL
    DOMAIN = "hitomi.la"

    def __post_init__(self) -> None:
        self.headers = {"Referer": str(PRIMARY_URL)}
        self._servers: Servers = None  # type: ignore
        self._last_update: datetime

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in GALLERY_PARTS):
            return await self.gallery(scrape_item)
        raise ValueError

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
        url = LTN_SERVER / "galleries" / gallery_id
        async with self.request_limiter:
            js_text = await self.client.get_text(self.DOMAIN, url, self.headers)
        return json.loads(js_text.split("=", 1)[-1])

    async def get_servers(self) -> Servers:
        if self._servers and (datetime.now() - self._last_update < timedelta(minutes=40)):
            return self._servers
        self._servers = await self._get_servers()
        self._last_update = datetime.now()
        return self._servers

    async def _get_servers(self) -> Servers:
        # See: https://ltn.gold-usergeneratedcontent.net/gg.js
        url = LTN_SERVER / "gg.js"
        async with self.request_limiter:
            js_text = await self.client.get_text(self.DOMAIN, url)

        base, num, default_num = [
            match_int_or_none(pattern, js_text) for pattern in (_REGEX.BASE, _REGEX.NUM, _REGEX.DEFAULT_NUM)
        ]
        assert base is not None
        assert num is not None
        default_num = default_num if default_num is not None else 0
        servers = Servers(base, default_num)

        for match in re.finditer(_REGEX.CASES, js_text):
            case = match.group(1)
            servers[int(case)] = num + 1

        return servers

    async def process_gallery(self, scrape_item: ScrapeItem, gallery: Gallery) -> None:
        servers = await self.get_servers()
        gallery_reader_url = PRIMARY_URL / f"reader/{gallery['id']}.html"

        for index, image in enumerate(gallery["files"], 1):
            link = get_image_url(servers, image)
            reader_url = gallery_reader_url.with_fragment(str(index))
            new_scrape_item = scrape_item.create_child(reader_url)
            filename, ext = self.get_filename_and_ext(image["name"])
            custom_filename = Path(filename).with_suffix(link.suffix).as_posix()
            await self.handle_file(
                reader_url, new_scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
            )


def get_image_url(servers: Servers, image: Image) -> AbsoluteHttpURL:
    if ALLOW_AVIF and image.get("hasavif"):
        dir = "avif"
    else:
        dir = "webp"
    return url_from_hash(servers, image, dir, ext=f".{dir}")


def url_from_hash(servers: Servers, image: Image, dir: str, ext: str | None = None) -> AbsoluteHttpURL:
    # See: https://ltn.gold-usergeneratedcontent.net/common.js
    if ext is None:
        _, ext = get_filename_and_ext(image["name"])

    image_hash = image["hash"]
    server_hex_num = int(image_hash[-1] + image_hash[-3:-1], base=16)
    server_num = servers[server_hex_num]

    origin = AbsoluteHttpURL(f"https://{ext[0]}{server_num}.{CONTENT_HOST}")
    path = f"{servers.base}/{server_hex_num}/{image_hash}{ext}"
    if dir in ("webp", "avif"):
        return origin / path
    return origin / dir / path


def match_int_or_none(pattern: str, string: str) -> int | None:
    if match := re.search(pattern, string):
        return int(match.group(1).removesuffix("/"))
