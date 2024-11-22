from pathlib import Path

from pydantic import BaseModel, ByteSize, NonNegativeInt

from cyberdrop_dl.utils.constants import APP_STORAGE, BROWSERS

from .custom_types import AppriseURL, NonEmptyStr


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
    exclude_videos: bool
    exclude_images: bool
    exclude_audio: bool
    exclude_other: bool
    ignore_coomer_ads: bool
    skip_hosts: list[NonEmptyStr]
    only_hosts: list[NonEmptyStr]


class RuntimeOptions(BaseModel):
    ignore_history: bool
    log_level: int
    console_log_level: int
    skip_check_for_partial_files: bool
    skip_check_for_empty_folders: bool
    delete_partial_files: bool
    update_last_forum_post: bool
    send_unsupported_to_jdownloader: bool
    jdownloader_download_dir: Path | None
    jdownloader_autostart: bool
    jdownloader_whitelist: list[NonEmptyStr]


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
    browsers: list[BROWSERS]
    auto_import: bool
    sites: list[NonEmptyStr]


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
