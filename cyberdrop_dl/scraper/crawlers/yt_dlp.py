from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from typing import TYPE_CHECKING

from yarl import URL
from yt_dlp import YoutubeDL
from yt_dlp.extractor import gen_extractors
from yt_dlp.extractor.generic import GenericIE
from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError, UnsupportedError

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

EXTRACT_INFO_TIMEOUT = 10  # seconds
ALL_EXTRACTORS = gen_extractors()
PROPER_EXTRACTORS = [ie for ie in ALL_EXTRACTORS if ie != GenericIE]
INFO_FIELDS_TO_KEEP = [
    "filesize_approx",
    "filename",
    "epoch",
    "formats",
    "_has_drm",
    "is_live",
    "_type",
    "extractor",
    "extractor_key",
    "upload_date",
    "timestamp",
    "id",
    "http_headers",
    "requested_formats",
]
DEFAULT_EXTRACT_OPTIONS = {
    "quiet": True,
    "extract_flat": True,
}


# TODO: Convert to pydantic model
@dataclass(frozen=True, slots=True)
class YtDlpFormat:
    format_id: str
    ext: str
    protocol: str
    acodec: str | None
    vcodec: str | None
    audio_ext: str | None
    video_ext: str | None
    resolution: str | None
    filesize_approx: int
    http_headers: dict
    url: str

    @classmethod
    def from_dict(cls, format_dict: dict) -> YtDlpFormat:
        field_names = [f.name for f in fields(cls)]
        proper_dict = {k: v for k, v in format_dict.items() if k in field_names}
        return cls(**proper_dict)


class YtDlpCrawler(Crawler):
    primary_base_domain = URL("https://youtube.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "youtube", "Youtube")
        self.cookies_file = self.manager.path_manager.cookies_dir / "cookies.yt_dlp"
        self.archive_file = self.manager.path_manager.cache_folder / "yt_dlp_archive.txt"
        self.options = {"cookiefile": str(self.cookies_file), "download_archive": str(self.archive_file)}

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        scrape_item.url = clean_url(scrape_item.url)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem, info: dict | None = None) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        if info is None:
            info = await self.extract_info(scrape_item)
        if not info:
            return
        if await self.check_archive(info):
            return
        format_ids = format_selector(info)
        formats = get_formats(info, format_ids)
        formats_as_dict = [asdict(f) for f in formats]
        info = info | {"formats": formats}
        log_debug(json.dumps(info | {"formats": formats_as_dict}, indent=4))
        await self.process_formats(scrape_item, info)

    async def process_formats(self, scrape_item: ScrapeItem, info: dict) -> None:
        formats: list[YtDlpFormat] = info["formats"]
        assert formats
        assert isinstance(formats[0], YtDlpFormat)
        for fmt in formats:
            link = self.parse_url(fmt.url)
            filename, ext = get_filename_and_ext(f"{info["filename"]}.{fmt.ext}")
            database_url = create_db_url(info)
            # headers = fmt.http_headers
            await self.handle_file(database_url, scrape_item, filename, ext, debrid_link=link)

    @staticmethod
    def is_supported(url: URL) -> bool:
        """Checks if an URL is supported without making any request"""
        url = clean_url(url)
        for extractor in PROPER_EXTRACTORS:
            if extractor.suitable(str(url)):
                return True
        return False

    async def extract_info(self, scrape_item: ScrapeItem, **options) -> dict:
        """Helper function to add cookies and archive file before calling yt-dlp"""
        options = options | self.options
        return await extract_info_async(scrape_item, **options)

    async def check_archive(self, info: dict) -> bool:
        def is_in_archive():
            with yt_dlp_context(**self.options) as ydl:
                return ydl.in_download_archive(info)

        return await asyncio.to_thread(is_in_archive)


def format_selector(info: dict) -> tuple[str]:
    """Select the best video with audio"""

    formats = info["formats"][::-1]  # formats are sorted worst to best
    best_video = next(f for f in formats if f["vcodec"] != "none" and f["acodec"] != "none")
    return (best_video["format_id"],)


def format_selector_ffmpeg(info: dict) -> tuple[str, str]:
    """Select the best video and the best audio (requires ffmpeg for muxing)"""

    formats = info["formats"][::-1]  # formats are sorted worst to best
    best_video = next(f for f in formats if f["vcodec"] != "none" and f["acodec"] == "none")
    audio_ext = {"mp4": "m4a", "webm": "webm"}[best_video["ext"]]
    best_audio = next(f for f in formats if (f["acodec"] != "none" and f["vcodec"] == "none" and f["ext"] == audio_ext))
    return (best_video["format_id"], best_audio["format_id"])


def get_formats(info: dict, format_ids: Sequence) -> list[YtDlpFormat]:
    if isinstance(format_ids, str):
        format_ids = format_ids.split("+")
    formats = info["formats"]
    return [YtDlpFormat.from_dict(f) for f in formats if f["format_id"] in format_ids]


def extract_info(scrape_item: ScrapeItem, **options) -> dict:
    url_as_str = str(scrape_item.url)
    try:
        with yt_dlp_context(**options) as ydl:
            info: dict | list = ydl.sanitize_info(ydl.extract_info(url_as_str, download=False))  # type: ignore
            if isinstance(info, list):
                msg = "URL have multiple children. Only URLs of single media items (1 single video) are supported"
                log(msg, 40)
                return {}
            info["filename"] = ydl.prepare_filename(info)
            return {k: v for k, v in info.items() if k in INFO_FIELDS_TO_KEEP}
    except UnsupportedError:
        return {}
    except (DownloadError, ExtractorError, GeoRestrictedError) as e:
        raise ScrapeError("YT-DLP Error", e.msg, origin=scrape_item) from e
    return {}


async def extract_info_async(scrape_item: ScrapeItem, **options):
    async def _extract_info_async() -> dict:
        return await asyncio.to_thread(extract_info, scrape_item, **options)

    try:
        # Using a timeout it required cause some URLs could take several minutes to return (ex: youtube paylist)
        return await asyncio.wait_for(_extract_info_async(), timeout=EXTRACT_INFO_TIMEOUT)
    except TimeoutError:
        msg = f"Processing of {scrape_item.url} took too long"
        log(msg, 40)
        return {}


def clean_url(url: URL) -> URL:
    """Convert some known URL to individual item URL when possible"""
    assert url.host
    parsed_url = url
    if any(host in url.host for host in ("youtube", "y.tube")):
        video_id = url.query.get("v")
        assert video_id
        parsed_url = parsed_url.with_query(v=video_id)
    return parsed_url


def create_db_url(info: dict) -> URL:
    return URL(f"//yt-dlp/{info["extractor"]}/{info["id"]}")


@contextmanager
def yt_dlp_context(**options) -> Generator[YoutubeDL]:
    if not options:
        options = {}
    options = options | DEFAULT_EXTRACT_OPTIONS
    try:
        with YoutubeDL(options) as ydl:
            yield ydl
    finally:
        pass
