from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NamedTuple

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css, javascript
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup, Tag
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

PRIMARY_URL = AbsoluteHttpURL("https://www.eporner.com/")


class Selectors:
    DOWNLOADS = "div#hd-porn-dload > div.dloaddivcol"
    PHOTO = "div#gridphoto > a.photohref"
    VIDEO = "div[id^='vf'] div.mbcontent a"
    NEXT_PAGE = "div.numlist2 a.nmnext"
    H264 = "span.download-h264 > a"
    AV1 = "span.download-av1 > a"
    PROFILE_GALLERY = "div[id^='pf'] a"
    PROFILE_PLAYLIST = "div.streameventsday.showAll > div#pl > a"
    DATE_JS = "main script:contains('uploadDate')"
    GALLERY_TITLE = "div#galleryheader > h1"


_SELECTORS = Selectors()

RESOLUTIONS = ["4k", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]  # best to worst
ALLOW_AV1 = True
PROFILE_URL_PARTS = {
    "pics": ("uploaded-pics", _SELECTORS.PROFILE_GALLERY),
    "videos": ("uploaded-videos", _SELECTORS.VIDEO),
    "playlists": ("playlists", _SELECTORS.PROFILE_PLAYLIST),
}


class VideoInfo(NamedTuple):
    codec: str  # av1 > h264
    resolution: str
    size: str
    link_str: str

    @classmethod
    def from_tag(cls, tag: Tag) -> VideoInfo:
        link_str: str = css.get_attr(tag, "href")
        name = tag.get_text(strip=True).removeprefix("Download")
        details = name.split("(", 1)[1].removesuffix(")").split(",")
        res, codec, size = [d.strip() for d in details]
        codec = codec.lower()
        return cls(codec, res, size, link_str)


class EpornerCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Categories": "/cat/...",
        "Channels": "/channel/...",
        "Pornstar": "/pornstar/...",
        "Profile": "/profile/...",
        "Search": "/search/...",
        "Video": ("/<video_name>-<video-id>", "/hd-porn/<video_id>", "/embed/<video_id>"),
        "Photo": "/photo/...",
        "Gallery": "/gallery/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "eporner"
    FOLDER_DOMAIN: ClassVar[str] = "ePorner"
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if get_video_id(scrape_item.url):
            return await self.video(scrape_item)
        if any(p in scrape_item.url.parts for p in ("cat", "channel", "search", "pornstar")):
            return await self.playlist(scrape_item)
        if "gallery" in scrape_item.url.parts:
            return await self.gallery(scrape_item)
        if "profile" in scrape_item.url.parts:
            return await self.profile(scrape_item)
        if "photo" in scrape_item.url.parts:
            return await self.photo(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def profile(self, scrape_item: ScrapeItem) -> None:
        username = scrape_item.url.parts[2]
        canonical_url = PRIMARY_URL / "profile" / username
        if canonical_url in scrape_item.parents and "playlist" in scrape_item.url.parts:
            await self.playlist(scrape_item, from_profile=True)

        title = self.create_title(f"{username} [user]")
        scrape_item.setup_as_profile(title)

        parts_to_scrape = {}
        for name, parts in PROFILE_URL_PARTS.items():
            if any(p in scrape_item.url.parts for p in (name, parts[0])):
                parts_to_scrape = {name: parts}
                break

        scrape_item.url = canonical_url
        parts_to_scrape = parts_to_scrape or PROFILE_URL_PARTS
        for name, parts in parts_to_scrape.items():
            part, selector = parts
            url = canonical_url / part
            async for soup in self.web_pager(url):
                for _, new_scrape_item in self.iter_children(scrape_item, soup, selector, new_title_part=name):
                    self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem, from_profile: bool = False) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title and not from_profile:
                title = css.select_one_get_text(soup, "title")
                title_trash = "Porn Star Videos", "Porn Videos", "Videos -", "EPORNER"
                for trash in title_trash:
                    title = title.rsplit(trash)[0].strip()
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEO):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = css.select_one_get_text(soup, _SELECTORS.GALLERY_TITLE)
                title = self.create_title(title)
                scrape_item.setup_as_album(title)

            for thumb, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.PROFILE_GALLERY):
                assert thumb
                filename = thumb.name.rsplit("-", 1)[0]
                filename, ext = self.get_filename_and_ext(f"{filename}{thumb.suffix}")
                link = thumb.with_name(filename)
                await self.handle_file(link, new_scrape_item, filename, ext)

    @error_handling_wrapper
    async def photo(self, scrape_item: ScrapeItem) -> None:
        photo_id = scrape_item.url.parts[2]
        canonical_url = PRIMARY_URL / "photo" / photo_id
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        scrape_item.url = canonical_url
        img = soup.select_one(_SELECTORS.PHOTO)
        if not img:
            raise ScrapeError(422)
        link_str: str = css.get_attr(img, "href")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        video_id = get_video_id(scrape_item.url)
        canonical_url = PRIMARY_URL / f"video-{video_id}"
        if await self.check_complete_from_referer(canonical_url):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        soup_str = soup.text
        if "File has been removed due to copyright owner request" in soup_str:
            raise ScrapeError(451)
        if "Video has been deleted" in soup_str:
            raise ScrapeError(410)

        scrape_item.url = canonical_url
        info_dict = get_info_dict(soup)
        resolution, link_str = get_best_quality(soup)
        if not link_str:
            raise ScrapeError(422)

        link = self.parse_url(link_str)
        scrape_item.possible_datetime = self.parse_date(info_dict["uploadDate"])
        filename, ext = self.get_filename_and_ext(link.name)
        if ext == ".m3u8":
            raise ScrapeError(422)
        custom_filename = self.create_custom_filename(info_dict["name"], ext, file_id=video_id, resolution=resolution)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)


def get_available_resolutions(soup: BeautifulSoup) -> list[VideoInfo]:
    downloads = soup.select_one(_SELECTORS.DOWNLOADS)
    assert downloads
    formats = downloads.select(_SELECTORS.H264)
    if ALLOW_AV1:
        formats.extend(downloads.select(_SELECTORS.AV1))
    return [VideoInfo.from_tag(tag) for tag in formats]


def get_best_quality(soup: BeautifulSoup) -> tuple[str, str]:
    """Returns name and URL of the best available quality.

    Returns URL as `str`"""
    formats = get_available_resolutions(soup)
    best_format = formats[0]
    formats_dict: dict[str, list[VideoInfo]] = {}
    for res in RESOLUTIONS:
        formats_dict[res] = sorted(f for f in formats if f.resolution == res)

    for res in RESOLUTIONS:
        available_formats = formats_dict.get(res)
        if available_formats:
            best_format = available_formats[0]
            break

    return best_format.resolution, best_format.link_str


def get_info_dict(soup: BeautifulSoup) -> dict:
    info_js_script = css.select_one_get_text(soup, _SELECTORS.DATE_JS)
    info_dict: dict = javascript.parse_json_to_dict(info_js_script, use_regex=False)
    javascript.clean_dict(info_dict)
    return info_dict


def get_video_id(url: URL) -> str:
    if "video-" in url.parts[1]:
        return url.parts[1].rsplit("-", 1)[1]
    if any(p in url.parts for p in ("hd-porn", "embed")) and len(url.parts) > 2:
        return url.parts[2]
    return ""
