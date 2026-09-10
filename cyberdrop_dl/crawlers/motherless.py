from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, final, override

from cyberdrop_dl import aio
from cyberdrop_dl.clients.http import HTTPConfig
from cyberdrop_dl.crawlers import Registry
from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import TextExtractor, css, dates, json_ld, parse_url
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    import datetime
    from collections.abc import AsyncIterable, Generator

    from bs4 import BeautifulSoup

    from cyberdrop_dl.url_objects import ScrapeItem


@final
class Selector:
    MEDIA_INFO_JS = "script:-soup-contains('__fileurl')"
    THUMB = ".thumb-container [data-codename]"
    COLLECTION_TITLE = ".gallery-title > h2, .group-bio > h1"
    USER_NAME = "div.member-bio-username"


@Registry.database.fix_referer
@HTTPConfig(rate_limit=(2, 1))
class MotherlessCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Group": (
            "/g/<group_name>",
            "/gi/<group_name>",
            "/gv/<group_name>",
        ),
        "Gallery": (
            "/G<gallery_id>",
            "/GI<gallery_id>",
            "/GV<gallery_id>",
        ),
        "User": (
            "/m/<user_name>",
            "/member/<user_name>",
            "/u/<user_name>",
            "/u/<user_name>?t=v",
            "/u/<user_name>?t=i",
        ),
        "User galleries": "/galleries/member/<user_name>/...",
        "Image or Video": (
            "/<media_id>",
            "/g/<group_name>/<media_id>",
            "/G<gallery_id>/<media_id>",
        ),
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://motherless.xxx")
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".pagination_link > a[rel=next]"
    DOMAIN: ClassVar[str] = "motherless"
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ("motherless.com",)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        match scrape_item.url.parts[1:]:
            case ["g", slug]:
                await self.group(scrape_item, slug)
            case ["gv" | "gi" as prefix, slug]:
                name = "images" if prefix == "gi" else "videos"
                await self.collection(scrape_item, slug, name)

            case [slug] if slug.startswith("G") and (gallery_id := slug[2:]):
                if (prefix := slug[:2]) in ("GV", "GI"):
                    name = "images" if prefix == "GI" else "videos"
                    return await self.collection(scrape_item, gallery_id, name)

                gallery_id = slug[1:]
                await self.gallery(scrape_item, gallery_id)

            case [media_id]:
                await self.media(scrape_item, media_id)

            case ["u", username]:
                type_ = scrape_item.url.query.get("t")
                if type_ not in ("v", "i"):
                    return await self.user(scrape_item, username)
                name = "images" if type_ == "i" else "videos"
                await self.user_collection(scrape_item, username, name)

            case ["galleries", "member", username, *_]:
                await self.user_collection(scrape_item, username, "galleries")

            case _:
                raise ValueError

    @classmethod
    @override
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        url = super().transform_url(url)
        match url.parts[1:]:
            case [slug, media_id] if slug.startswith("G") and slug[1:]:
                return url.origin() / media_id
            case ["g", _, media_id]:
                return url.origin() / media_id
            case ["member" | "m", username]:
                return url.origin() / "u" / username
            case _:
                return url

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem, gallery_id: str) -> None:
        for part in ("GI", "GV"):
            new_item = scrape_item.copy()
            new_item.url = self.PRIMARY_URL / f"{part}{gallery_id}"
            self.create_task(self.run(new_item))

    @error_handling_wrapper
    async def group(self, scrape_item: ScrapeItem, slug: str) -> None:
        for part in ("gi", "gv"):
            new_item = scrape_item.copy()
            new_item.url = self.PRIMARY_URL / part / slug
            self.create_task(self.run(new_item))

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem, username: str) -> None:
        for part in ("i", "v"):
            new_item = scrape_item.copy()
            new_item.url = (self.PRIMARY_URL / "u" / username).with_query(t=part)
            self.create_task(self.run(new_item))

    @error_handling_wrapper
    async def user_collection(self, scrape_item: ScrapeItem, username: str, name: str) -> None:
        scrape_item.setup_as_album(self.create_title(f"{username} [user]"))
        scrape_item.append_folders(name)
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        _check_soup(soup)
        await self._iter_media(scrape_item, pages)

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem, collection_id: str, name: str) -> None:
        soup, pages = await aio.peek_first(self.web_pager(scrape_item.url))
        _check_soup(soup)
        title = self.create_title(css.select_text(soup, Selector.COLLECTION_TITLE), collection_id)
        scrape_item.setup_as_album(title, album_id=collection_id)
        scrape_item.append_folders(name)
        await self._iter_media(scrape_item, pages)

    async def _iter_media(self, scrape_item: ScrapeItem, pages: AsyncIterable[BeautifulSoup]) -> None:
        async for soup in pages:
            for media in _extract_media_from_thumbs(soup):
                url = self.parse_url(media.href)
                new_item = scrape_item.create_child(url)
                if media.type == "image" and Path(url.name).stem == media.code:
                    self.create_eager_task(self._media(new_item, media))
                else:
                    self.create_eager_task(self.run(new_item))

                scrape_item.add_children()

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem, _media_id: str) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return

        soup = await self.request_soup(scrape_item.url)
        _check_soup(soup)
        await self._media(scrape_item, _extract_media(soup))

    @error_handling_wrapper
    async def _media(self, scrape_item: ScrapeItem, media: Media) -> None:
        scrape_item.upload_date = media.upload_date
        scrape_item.url = self.PRIMARY_URL / media.code
        _, ext = self.get_filename_and_ext(media.src.name)
        filename = self.create_custom_filename(media.name, ext, file_id=media.code)
        await self.handle_file(media.src, scrape_item, media.name, ext, custom_filename=filename)


def _check_soup(soup: BeautifulSoup) -> None:
    html = soup.get_text()
    for txt in ("The page you're looking for cannot be found", "File not Found. Nothing to see here"):
        if txt in html:
            raise ScrapeError(404)
    if "The content you are trying to view is for friends only" in html:
        raise ScrapeError(401)


@dataclasses.dataclass(slots=True)
class Media:
    type: str
    code: str
    name: str
    href: str
    src: AbsoluteHttpURL
    upload_date: datetime.datetime | None


def _extract_media_from_thumbs(soup: BeautifulSoup) -> Generator[Media]:
    for thumb in css.iselect(soup, Selector.THUMB):
        static = css.select(thumb, "img.static")
        media_type = css.attr(thumb, "data-mediatype")
        name = css.attr(static, "alt")
        if name.startswith("Shared by"):
            assert "-" in name
            name = name.partition("-")[0]

        yield Media(
            type=media_type,
            code=css.attr(thumb, "data-codename"),
            name=css.unescape(name),
            href=css.select(thumb, "a.img-container", "href"),
            src=parse_url(css.attr(static, "src").replace("thumb", media_type)),
            upload_date=None,
        )


def _extract_media(soup: BeautifulSoup) -> Media:
    js_text = css.select_text(soup, Selector.MEDIA_INFO_JS)
    extract = TextExtractor(js_text)
    _, props = json_ld.find(soup, "uploadDate")
    return Media(
        name=props["name"],
        upload_date=dates.parse_iso(props["uploadDate"]),
        type=extract("__mediatype = '", "'"),
        code=extract("__codename = '", "'"),
        href="",
        src=parse_url(extract("__fileurl = '", "'")),
    )
