from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Required, TypedDict

from pydantic import BaseModel, Field
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

PRIMARY_BASE_DOMAIN = URL("https://hitomi.la/")
GALLERY_PARTS = "cg", "doujinshi", "galleries", "gamecg", "imageset", "manga", "reader"
TAG_PARTS = "artist", "character", "group", "series", "tag", "type"

CONTENT_HOST = "gold-usergeneratedcontent.net"
LTN_SERVER = URL(f"https://ltn.{CONTENT_HOST}/")
ALLOW_AVIF = False


class Image(TypedDict, total=False):
    hash: Required[str]
    name: Required[str]
    hasavif: int


class Gallery(BaseModel):
    blocked: bool
    id: str = Field(coerce_numbers_to_str=True)
    title: str
    files: list[Image]
    galleryurl: str
    type: str
    datepublished: datetime | None
    date: datetime

    # TODO: Support videos
    video: str | None
    language_localname: str
    videofilename: str | None
    language: str
    japanese_title: str
    language_url: str

    @property
    def url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / self.galleryurl

    @property
    def reader_url(self) -> URL:
        return PRIMARY_BASE_DOMAIN / f"reader/{self.id}.html"

    @property
    def timestamp(self) -> int:
        date = self.datepublished or self.date
        return calendar.timegm(date.timetuple())


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


class HitomiLaCrawler(Crawler):
    primary_base_domain = PRIMARY_BASE_DOMAIN

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "hitomi.la", "Hitomi.La")
        self._servers: Servers = field(init=False)
        self._last_update: datetime = field(init=False)
        self.headers = {"Referer": str(PRIMARY_BASE_DOMAIN)}

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if any(p in scrape_item.url.parts for p in GALLERY_PARTS):
            return await self.gallery(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        gallery_id = scrape_item.url.name.split("-")[-1].removesuffix(".html")
        gallery = await self.get_gallery(gallery_id)
        if gallery.blocked:
            raise ScrapeError(403)

        title = self.create_title(f"{gallery.title} [{gallery.type}]", gallery.id)
        scrape_item.setup_as_album(title, album_id=gallery.id)
        scrape_item.possible_datetime = gallery.timestamp
        await self.process_gallery(scrape_item, gallery)

    async def get_gallery(self, gallery_id: str) -> Gallery:
        url = LTN_SERVER / "galleries" / gallery_id
        async with self.request_limiter:
            js_text = await self.client.get_text(self.domain, url, self.headers)

        gallery_dict = js_text.split("=", 1)[-1]
        return Gallery.model_validate(gallery_dict)

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
            js_text = await self.client.get_text(self.domain, url)

        def match_int_or_none(pattern: str) -> int | None:
            if match := re.search(pattern, js_text):
                return int(match.group(1).removesuffix("/"))

        patterns = _REGEX.BASE, _REGEX.NUM, _REGEX.DEFAULT_NUM
        base, num, default_num = [match_int_or_none(pattern) for pattern in patterns]
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
        for index, image in enumerate(gallery.files, 1):
            link = get_image_url(servers, image)
            reader_url = gallery.reader_url.with_fragment(str(index))
            new_scrape_item = scrape_item.create_child(reader_url)
            filename, ext = self.get_filename_and_ext(image["name"])
            custom_filename = Path(filename).with_suffix(link.suffix).as_posix()
            await self.handle_file(
                reader_url, new_scrape_item, filename, ext, custom_filename=custom_filename, debrid_link=link
            )


def get_image_url(servers: Servers, image: Image) -> URL:
    if ALLOW_AVIF and image.get("hasavif"):
        ext = ".avif"
    else:
        ext = ".webp"
    dir = ext.removeprefix(".")
    return url_from_hash(servers, image, dir, ext)


def url_from_hash(servers: Servers, image: Image, dir: str, ext: str | None = None) -> URL:
    # See: https://ltn.gold-usergeneratedcontent.net/common.js
    if ext is None:
        _, ext = get_filename_and_ext(image["name"])

    image_hash = image["hash"]
    server_hex_num = int(image_hash[-1] + image_hash[-3:-1], base=16)
    server_num = servers[server_hex_num]

    origin = URL(f"https://{ext[0]}{server_num}.{CONTENT_HOST}")
    path = f"{servers.base}/{server_hex_num}/{image_hash}{ext}"
    if dir in ("webp", "avif"):
        return origin / path
    return origin / dir / path
