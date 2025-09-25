from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


PRIMARY_URL = AbsoluteHttpURL("https://motherless.com")
MEDIA_INFO_JS_SELECTOR = "script:-soup-contains('__fileurl')"
ITEM_SELECTOR = "div.thumb-container a.img-container"
ITEM_TITLE_SELECTOR = "div.media-meta-title"
GALLERY_TITLE_SELECTOR = "div.gallery-title > h2"
GROUP_TITLE_SELECTOR = "div.group-bio > h1"
ITEM_GALLERY_TITLE_SELECTOR = "div.gallery-captions > a.gallery-data"
NOT_FOUND_TEXTS = "The page you're looking for cannot be found", "File not Found. Nothing to see here"
USER_NAME_SELECTOR = "div.member-bio-username"


class MediaInfo(NamedTuple):
    type: str
    url: str


class MotherlessCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Group": ("/g/<group_name>", "/gi/<image>", "/gv/<video>"),
        "User": ("/u/...", "/f/..."),
        "Image": "/...",
        "Video": "pending",
        "**NOTE**": "Galleries are NOT supported",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "div.pagination_link > a[rel=next]"
    DOMAIN: ClassVar[str] = "motherless"
    _RATE_LIMIT = 2, 1

    async def fetch(self, scrape_item: ScrapeItem, collection_id: str = "") -> None:
        parts = scrape_item.url.parts
        n_parts = len(parts)
        item_id = collection_id or scrape_item.url.name
        is_gallery_homepage = scrape_item.url.name.startswith("G") and n_parts == 2
        is_group_homepage = "g" in parts and n_parts == 3
        is_user = any(p in parts for p in ("u", "f"))  # /member/ is for user galleries, not supported yet
        is_videos_or_images = any(p in parts for p in ("videos", "images"))
        is_supported_user_url = is_user and (n_parts == 3 or (n_parts > 3 and is_videos_or_images))

        if "gi" in parts:  # group images
            return await self.collection_items(scrape_item, "images", item_id)
        if "gv" in parts:  # group videos
            return await self.collection_items(scrape_item, "videos", item_id)
        if is_group_homepage or is_gallery_homepage:  # gallery or group
            return await self.collection(scrape_item)
        if is_supported_user_url:
            return await self.user(scrape_item)
        if is_user:
            raise ValueError
        return await self.media(scrape_item)

    @error_handling_wrapper
    async def user(self, scrape_item: ScrapeItem) -> None:
        n_parts = len(scrape_item.url.parts)
        assert n_parts >= 3
        username = scrape_item.url.parts[2]
        canonical_url = PRIMARY_URL / "f" / username
        videos_url = canonical_url / "videos"
        images_url = canonical_url / "images"
        is_homepage = n_parts == 3

        title: str = f"{username} [user]"
        title = self.create_title(title)
        scrape_item.setup_as_album(title)

        if is_homepage or "images" in scrape_item.url.parts:
            async for soup in self.web_pager(images_url):
                check_soup(soup)
                for _, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR, new_title_part="Images"):
                    self.create_task(self.run(new_scrape_item))

        if is_homepage or "videos" in scrape_item.url.parts:
            async for soup in self.web_pager(videos_url):
                check_soup(soup)
                for _, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR, new_title_part="Videos"):
                    self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def collection(self, scrape_item: ScrapeItem) -> None:
        group_id = scrape_item.url.name
        gallery_id = group_id.removeprefix("G")
        media_types = "images", "videos"
        is_group = "g" in scrape_item.url.parts
        if not is_group and gallery_id.startswith("G"):  # No support for subgalleries
            raise ScrapeError(422)

        for prefix in ("I", "V"):
            gallery_id = gallery_id.removeprefix(prefix)

        if is_group:
            new_urls = [PRIMARY_URL / part / group_id for part in ("gi", "gv")]

        else:
            new_urls = [PRIMARY_URL / f"{part}{gallery_id}" for part in ("GI", "GV")]

        collection_id = group_id if is_group else gallery_id
        for media_type, url in zip(media_types, new_urls, strict=True):
            new_scrape_item = scrape_item.create_child(url)
            await self.collection_items(new_scrape_item, media_type, collection_id)

    @error_handling_wrapper
    async def collection_items(
        self, scrape_item: ScrapeItem, media_type: Literal["videos", "images"], collection_id: str | None = None
    ) -> None:
        title = ""
        name = media_type.capitalize()
        async for soup in self.web_pager(scrape_item.url):
            check_soup(soup)
            if not title:
                title_tag = soup.select_one(GALLERY_TITLE_SELECTOR) or soup.select_one(GROUP_TITLE_SELECTOR)
                assert title_tag
                title: str = title_tag.get_text(strip=True)
                title = self.create_title(title, collection_id)
                scrape_item.setup_as_album(title, album_id=collection_id)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, ITEM_SELECTOR, new_title_part=name):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def media(self, scrape_item: ScrapeItem) -> None:
        media_id = scrape_item.url.parts[-1]
        canonical_url = PRIMARY_URL / media_id

        if await self.check_complete_from_referer(canonical_url):
            return

        soup = await self.request_soup(scrape_item.url)

        check_soup(soup)
        media_info = self.process_media_soup(scrape_item, soup)
        link = self.parse_url(media_info.url)
        scrape_item.url = canonical_url
        title = css.select_one_get_text(soup, ITEM_TITLE_SELECTOR)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(title, ext, file_id=media_id)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def process_media_soup(self, scrape_item: ScrapeItem, soup: BeautifulSoup) -> MediaInfo:
        media_info = get_media_info(soup)
        if media_info.type == "gallery":
            raise ScrapeError(422)

        n_parts = len(scrape_item.url.parts)
        from_gallery = n_parts > 2 and scrape_item.url.parts[1].startswith("G")
        from_group = n_parts > 3 and "g" in scrape_item.url.parts
        if not (from_gallery or from_group):
            return media_info

        parent_id = scrape_item.url.parts[2] if from_group else scrape_item.url.parts[1]
        parent_title = ""
        title_tag = soup.select_one(ITEM_GALLERY_TITLE_SELECTOR)
        if from_gallery:
            parent_id = parent_id.removeprefix("G")
            title_tag = soup.select_one(GROUP_TITLE_SELECTOR)

        if title_tag:
            parent_title: str = css.get_attr(title_tag, "title") if from_gallery else title_tag.get_text(strip=True)

        parent_path = parent_id if from_gallery else f"g/{parent_id}"
        parent_url = PRIMARY_URL / parent_path
        if parent_url not in scrape_item.parents and parent_title:
            scrape_item.parents.append(parent_url)
            title = self.create_title(parent_title, parent_id)
            scrape_item.setup_as_album(title, album_id=parent_id)
            scrape_item.add_to_parent_title(f"{media_info.type.capitalize()}s")

        return media_info


def check_soup(soup: BeautifulSoup) -> None:
    soup_str = soup.get_text()
    if any(p in soup_str for p in NOT_FOUND_TEXTS):
        raise ScrapeError(404)
    if "The content you are trying to view is for friends only" in soup_str:
        raise ScrapeError(401)


def get_media_info(soup: BeautifulSoup) -> MediaInfo:
    media_js = soup.select_one(MEDIA_INFO_JS_SELECTOR)
    js_text = css.get_text(media_js) if media_js else None
    if not js_text:
        return MediaInfo("gallery", "")
    media_type = js_text.split("__mediatype", 1)[-1].split("=", 1)[-1].split(",", 1)[0].strip()
    url = js_text.split("__fileurl", 1)[-1].split("=", 1)[-1].split(";", 1)[0].strip()
    parts = remove_quotes(media_type.lower()), remove_quotes(url)
    return MediaInfo(*parts)


def remove_quotes(text: str) -> str:
    return text.removeprefix("'").removesuffix("'").removeprefix('"').removesuffix('"')
