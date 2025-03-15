from __future__ import annotations

import asyncio
import os
from functools import partialmethod
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from yarl import URL
from yt_dlp import YoutubeDL
from yt_dlp.extractor import gen_extractors
from yt_dlp.extractor.generic import GenericIE
from yt_dlp.utils import DownloadError as YtDlpDownloadError
from yt_dlp.utils import ExtractorError, GeoRestrictedError, UnsupportedError

from cyberdrop_dl.clients.errors import DownloadError
from cyberdrop_dl.utils.logger import log, log_with_color
from cyberdrop_dl.utils.utilities import get_download_path

if TYPE_CHECKING:
    from collections.abc import Generator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem


EXTRACT_INFO_TIMEOUT = 100  # seconds
ALL_EXTRACTORS = gen_extractors()
PROPER_EXTRACTORS = [ie for ie in ALL_EXTRACTORS if ie != GenericIE]
DEBUG_PREFIX = "[debug] "


class YtDlpLogger:
    def debug(self, msg: str, level: int = 20) -> None:
        if msg.startswith(DEBUG_PREFIX):
            return log_with_color(msg.removeprefix(DEBUG_PREFIX), "", 10, show_in_stats=False)
        log_with_color(msg, "", level, show_in_stats=False)

    info = partialmethod(debug, level=20)
    warning = partialmethod(debug, level=30)
    error = partialmethod(debug, level=40)


DEFAULT_EXTRACT_OPTIONS = {
    "quiet": True,
    "extract_flat": False,
    "skip_download": True,
    "simulate": True,
    "logger": YtDlpLogger(),
}

FOLDER_DOMAIN = "yt-dlp"
YT_DLP_BANNED_HOST = {}


class Video(NamedTuple):
    url: URL
    download_path: Path

    @property
    def options(self) -> dict[str, dict | str]:
        return {"outtmpl": {"default": str(self.download_path)}}


class YtDlpManager:
    def __init__(self) -> None:
        """self.manager = manager
        self.cookies_file = self.manager.path_manager.cookies_dir / "cookies.yt_dlp"
        self.archive_file = self.manager.path_manager.cache_folder / "yt_dlp_archive.txt"
        self.config_file = self.manager.path_manager.config_folder / "yt_dlp_options.txt"
        self.options = {
            "cookiefile": str(self.cookies_file.resolve()),
            "download_archive": str(self.archive_file.resolve()),
            "config_location": str(self.config_file.resolve()),
        }"""
        self.items: list[Video] = []
        self.manager = None
        self.output_script = Path("yt_dlp_run.bat")

    async def process_item(self, scrape_item: ScrapeItem) -> None:
        log(f"Using yt-dlp for unsupported URL: {scrape_item.url}", 10)
        info = await get_info_async(scrape_item.url, **DEFAULT_EXTRACT_OPTIONS)
        print(info)  # noqa: T201
        for video_info in get_videos(info):
            print(video_info)  # noqa: T201
            url = video_info["url"]
            if in_download_archive_async(video_info):
                log(f"Skipping {url} as it has already been downloaded", 10)
                continue

            path = get_output_template(scrape_item, self.manager)
            self.items.append(Video(url, path))

    @staticmethod
    def is_supported(url: URL) -> bool:
        """Checks if an URL is supported without making any request"""
        if url.host and url.host not in YT_DLP_BANNED_HOST:
            for extractor in PROPER_EXTRACTORS:
                if extractor.suitable(str(url)):
                    return True
        return False

    def run(self):
        download(*self.items)

    def create_run_script(self) -> None:
        header = "#! /usr/bin/env sh"
        if os.name == "nt":
            header = "@echo off"

        self.output_script.write_text(header + "\n", "utf8")
        for video in self.items:
            command = f"yt-dlp {video.url} -o {video.download_path}"
            self.output_script.write_text(command + "\n", "utf8")


## ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~``


def get_output_template(scrape_item: ScrapeItem, manager: Manager | None) -> Path:
    format = "%(uploader)s/%(title)s.%(ext)s"
    if not manager:
        return Path(format)
    return get_download_path(manager, scrape_item, FOLDER_DOMAIN) / format


async def get_info_async(url: URL, **options) -> dict:
    async def get_info_to_thread():
        return await asyncio.to_thread(get_info, url, **options)

    try:
        # Using a timeout it required cause some URLs could take several minutes to return (ex: youtube paylist)
        return await asyncio.wait_for(get_info_to_thread(), timeout=EXTRACT_INFO_TIMEOUT)
    except TimeoutError:
        msg = f"Processing of {url} took too long"
        log(msg, 40)
        return {}


async def in_download_archive_async(info: dict, **options) -> bool:
    return await asyncio.to_thread(in_download_archive, info, **options)


def download(*videos: Video) -> None:
    for video in videos:
        url_as_str = str(video.url)
        try:
            with YoutubeDL(video.options) as ydl:
                ydl.download(url_as_str)
        except (YtDlpDownloadError, ExtractorError, GeoRestrictedError) as e:
            raise DownloadError("YT-DLP Error", e.msg) from e


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def get_videos(info_dict: dict) -> Generator[dict]:
    if info_dict.get("_type") == "playlist" and "entries" in info_dict:
        yield from info_dict["entries"]
    else:
        yield info_dict


def get_info(url: URL, **options) -> dict:
    url_as_str = str(url)
    try:
        with YoutubeDL(options) as ydl:
            info: dict = ydl.sanitize_info(ydl.extract_info(url_as_str, download=False))  # type: ignore
            return info
    except UnsupportedError:
        return {}
    except (YtDlpDownloadError, ExtractorError, GeoRestrictedError):
        # raise DownloadError("YT-DLP Error", e.msg) from e
        pass
    return {}


def in_download_archive(info: dict, **options) -> bool:
    with YoutubeDL(options) as ydl:
        return ydl.in_download_archive(info)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~`

if __name__ == "__main__":
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

    test_url = URL("https://www.youtube.com/playlist?list=PL8mG-RkN2uTyZZ00ObwZxxoG_nJbs3qec")
    scrape_item = ScrapeItem(url=test_url)
    instance = YtDlpManager()
    asyncio.run(instance.process_item(scrape_item))
    instance.create_run_script()
    # print(json.dumps(info))


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
