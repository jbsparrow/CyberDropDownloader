from enum import IntEnum
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, AnyHttpUrl, BaseModel, NonNegativeInt, StringConstraints
from yarl import URL

from cyberdrop_dl.utils import constants


def convert_to_yarl(value: AnyHttpUrl) -> URL:
    return URL(value)


VerifiedURL = Annotated[AnyHttpUrl, AfterValidator(convert_to_yarl)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class DownloadOptions(BaseModel):
    block_download_sub_folders: bool
    disable_download_attempt_limit: bool
    disable_file_timestamps: bool
    include_album_id_in_folder_name: bool
    include_thread_id_in_folder_name: bool
    remove_domains_from_folder_names: bool
    remove_generated_id_from_filenames: bool
    scrape_single_forum_post: bool
    separate_posts: bool
    skip_download_mark_completed: bool
    skip_referer_seen_before: bool
    maximum_number_of_children: list[NonNegativeInt]


class Files(BaseModel):
    input_file: Path
    download_folder: Path


class AppriseURL:
    def __init__(self, url: URL | str):
        self.value = url
        self.tags = None
        if isinstance(url, URL):
            self.url = url
            return
        parts = url.split("://", 1)[0].split("=", 1)
        if len(parts) == 2:
            self.tags = parts[0].split(",")
        self.url = URL(parts[-1])


class Logs(BaseModel):
    log_folder: Path = constants.APP_STORAGE / "Configs" / "{config}" / "Logs"
    webhook_url: VerifiedURL | None = None
    main_log_filename: NonEmptyStr = "downloader.log"
    last_forum_post_filename: NonEmptyStr = "Last_Scraped_Forum_Posts.csv"
    unsupported_urls_filename: NonEmptyStr = "Unsupported_URLs.csv"
    download_error_urls_filename: NonEmptyStr = "Download_Error_URLs.csv"
    scrape_error_urls_filename: NonEmptyStr = "Scrape_Error_URLs.csv"
    rotate_logs: bool = False


class FileSizeLimits(BaseModel):
    maximum_image_size: NonNegativeInt = 0
    maximum_other_size: NonNegativeInt = 0
    maximum_video_size: NonNegativeInt = 0
    minimum_image_size: NonNegativeInt = 0
    minimum_other_size: NonNegativeInt = 0
    minimum_video_size: NonNegativeInt = 0


class IgnoreOptions(BaseModel):
    exclude_videos: bool
    exclude_images: bool
    exclude_audio: bool
    exclude_other: bool
    ignore_coomer_ads: bool
    skip_hosts: list[str]
    only_hosts: list[str]


class LogLevel(IntEnum):
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10
    NOTSET = 0


class RuntimeOptions(BaseModel):
    ignore_history: bool
    log_level: LogLevel
    console_log_level: int
    skip_check_for_partial_files: bool
    skip_check_for_empty_folders: bool
    delete_partial_files: bool
    update_last_forum_post: bool
    send_unsupported_to_jdownloader: bool
    jdownloader_download_dir: Path | None
    jdownloader_autostart: bool
    jdownloader_whitelist: list[str]


class Sorting(BaseModel):
    sort_downloads: bool
    sort_folder: Path
    scan_folder: Path | None
    sort_cdl_only: bool
    sort_incremementer_format: NonEmptyStr
    sorted_audio: NonEmptyStr
    sorted_image: NonEmptyStr
    sorted_other: NonEmptyStr
    sorted_video: NonEmptyStr


class BrowserCookies(BaseModel):
    browsers: list[str]
    auto_import: bool
    sites: list[str]


class ConfigSettings(BaseModel):
    download_options: DownloadOptions
    files: Files
    logs: Logs
    file_size_limits: FileSizeLimits
    ignore_options: IgnoreOptions
    runtime_options: RuntimeOptions
    sorting: Sorting
    browser_cookies: BrowserCookies

Dupe_Cleanup_Options = {
        "hashing": "IN_PLACE",
        "auto_dedupe": True,
        "add_md5_hash": False,
        "add_sha256_hash": False,
        "send_deleted_to_trash": True,
    },
