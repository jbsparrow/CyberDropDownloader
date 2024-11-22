from logging import INFO
from pathlib import Path

from pydantic import BaseModel, ByteSize, NonNegativeInt

from cyberdrop_dl.utils.constants import APP_STORAGE, BROWSERS, DOWNLOAD_STORAGE

from .custom_types import AppriseURL, NonEmptyStr


class DownloadOptions(BaseModel):
    block_download_sub_folders: bool = False
    disable_download_attempt_limit: bool = False
    disable_file_timestamps: bool = False
    include_album_id_in_folder_name: bool = False
    include_thread_id_in_folder_name: bool = False
    remove_domains_from_folder_names: bool = False
    remove_generated_id_from_filenames: bool = False
    scrape_single_forum_post: bool = False
    separate_posts: bool = False
    skip_download_mark_completed: bool = False
    skip_referer_seen_before: bool = False
    maximum_number_of_children: list[NonNegativeInt] = []


class Files(BaseModel):
    input_file: Path = APP_STORAGE / "Configs" / "{config}" / "URLs.txt"
    download_folder: Path = DOWNLOAD_STORAGE


class Logs(BaseModel):
    log_folder: Path = APP_STORAGE / "Configs" / "{config}" / "Logs"
    webhook_url: AppriseURL | None = None
    main_log_filename: NonEmptyStr = "downloader.log"
    last_forum_post_filename: NonEmptyStr = "Last_Scraped_Forum_Posts.csv"
    unsupported_urls_filename: NonEmptyStr = "Unsupported_URLs.csv"
    download_error_urls_filename: NonEmptyStr = "Download_Error_URLs.csv"
    scrape_error_urls_filename: NonEmptyStr = "Scrape_Error_URLs.csv"
    rotate_logs: bool = False


class FileSizeLimits(BaseModel):
    maximum_image_size: ByteSize = 0
    maximum_other_size: ByteSize = 0
    maximum_video_size: ByteSize = 0
    minimum_image_size: ByteSize = 0
    minimum_other_size: ByteSize = 0
    minimum_video_size: ByteSize = 0


class IgnoreOptions(BaseModel):
    exclude_videos: bool = False
    exclude_images: bool = False
    exclude_audio: bool = False
    exclude_other: bool = False
    ignore_coomer_ads: bool = False
    skip_hosts: list[NonEmptyStr] = []
    only_hosts: list[NonEmptyStr] = []


class RuntimeOptions(BaseModel):
    ignore_history: bool = False
    log_level: int = INFO
    console_log_level: int = 100
    skip_check_for_partial_files: bool = False
    skip_check_for_empty_folders: bool = False
    delete_partial_files: bool = False
    update_last_forum_post: bool = True
    send_unsupported_to_jdownloader: bool = False
    jdownloader_download_dir: Path | None
    jdownloader_autostart: bool = False
    jdownloader_whitelist: list[NonEmptyStr] = []


class Sorting(BaseModel):
    sort_downloads: bool = False
    sort_folder: Path = DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"
    scan_folder: Path | None = None
    sort_cdl_only: bool = True
    sort_incremementer_format: NonEmptyStr = " ({i})"
    sorted_audio: NonEmptyStr = "{sort_dir}/{base_dir}/Audio/{filename}{ext}"
    sorted_image: NonEmptyStr = "{sort_dir}/{base_dir}/Images/{filename}{ext}"
    sorted_other: NonEmptyStr = "{sort_dir}/{base_dir}/Other/{filename}{ext}"
    sorted_video: NonEmptyStr = "{sort_dir}/{base_dir}/Videos/{filename}{ext}"


class BrowserCookies(BaseModel):
    browsers: list[BROWSERS]
    auto_import: bool = False
    sites: list[NonEmptyStr] = []


class ConfigSettings(BaseModel):
    browser_cookies: BrowserCookies
    download_options: DownloadOptions
    file_size_limits: FileSizeLimits
    files: Files
    ignore_options: IgnoreOptions
    logs: Logs
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
