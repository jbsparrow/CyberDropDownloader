import re
from datetime import timedelta
from logging import DEBUG
from pathlib import Path

from pydantic import BaseModel, ByteSize, Field, NonNegativeInt, PositiveInt, field_serializer, field_validator

from cyberdrop_dl.constants import APP_STORAGE, BROWSERS, DOWNLOAD_STORAGE
from cyberdrop_dl.data_structures.hash import Hashing
from cyberdrop_dl.data_structures.supported_domains import SUPPORTED_SITES_DOMAINS
from cyberdrop_dl.types import (
    AliasModel,
    ByteSizeSerilized,
    HttpAppriseURL,
    ListNonEmptyStr,
    ListNonNegativeInt,
    LogPath,
    MainLogPath,
    NonEmptyStr,
    NonEmptyStrOrNone,
    PathOrNone,
)
from cyberdrop_dl.utils.validators import parse_duration_as_timedelta, parse_falsy_as

ALL_SUPPORTED_SITES = ["<<ALL_SUPPORTED_SITES>>"]


class DownloadOptions(BaseModel):
    block_download_sub_folders: bool = False
    disable_download_attempt_limit: bool = False
    disable_file_timestamps: bool = False
    include_album_id_in_folder_name: bool = False
    include_thread_id_in_folder_name: bool = False
    maximum_number_of_children: ListNonNegativeInt = []
    remove_domains_from_folder_names: bool = False
    remove_generated_id_from_filenames: bool = False
    scrape_single_forum_post: bool = False
    separate_posts_format: NonEmptyStr = "{default}"
    separate_posts: bool = False
    skip_download_mark_completed: bool = False
    skip_referer_seen_before: bool = False
    maximum_thread_depth: NonNegativeInt = 0


class Files(AliasModel):
    download_folder: Path = Field(validation_alias="d", default=DOWNLOAD_STORAGE)
    dump_json: bool = Field(default=False, validation_alias="j")
    input_file: Path = Field(validation_alias="i", default=APP_STORAGE / "Configs" / "{config}" / "URLs.txt")
    save_pages_html: bool = False


class Logs(AliasModel):
    download_error_urls: LogPath = Field(
        default=Path("Download_Error_URLs.csv"), validation_alias="download_error_urls_filename"
    )
    last_forum_post: LogPath = Field(
        default=Path("Last_Scraped_Forum_Posts.csv"), validation_alias="last_forum_post_filename"
    )
    log_folder: Path = APP_STORAGE / "Configs" / "{config}" / "Logs"
    log_line_width: PositiveInt = Field(default=240, ge=50)
    logs_expire_after: timedelta | None = None
    main_log: MainLogPath = Field(default=Path("downloader.log"), validation_alias="main_log_filename")
    rotate_logs: bool = False
    scrape_error_urls: LogPath = Field(
        default=Path("Scrape_Error_URLs.csv"), validation_alias="scrape_error_urls_filename"
    )
    unsupported_urls: LogPath = Field(
        default=Path("Unsupported_URLs.csv"), validation_alias="unsupported_urls_filename"
    )
    webhook: HttpAppriseURL | None = Field(default=None, validation_alias="webhook_url")

    @field_validator("webhook", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        return parse_falsy_as(value, None)

    @field_validator("logs_expire_after", mode="before")
    @staticmethod
    def parse_logs_duration(input_date: timedelta | str | int | None) -> timedelta | str | None:
        return parse_falsy_as(input_date, None, parse_duration_as_timedelta)


class FileSizeLimits(BaseModel):
    maximum_image_size: ByteSizeSerilized = ByteSize(0)
    maximum_other_size: ByteSizeSerilized = ByteSize(0)
    maximum_video_size: ByteSizeSerilized = ByteSize(0)
    minimum_image_size: ByteSizeSerilized = ByteSize(0)
    minimum_other_size: ByteSizeSerilized = ByteSize(0)
    minimum_video_size: ByteSizeSerilized = ByteSize(0)


class MediaDurationLimits(BaseModel):
    maximum_video_duration: timedelta = timedelta(seconds=0)
    maximum_audio_duration: timedelta = timedelta(seconds=0)
    minimum_video_duration: timedelta = timedelta(seconds=0)
    minimum_audio_duration: timedelta = timedelta(seconds=0)

    @field_validator("*", mode="before")
    @staticmethod
    def parse_runtime_duration(input_date: timedelta | str | int | None) -> timedelta:
        """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.
        for `str`, the expected format is `value unit`, ex: `5 days`, `10 minutes`, `1 year`
        valid units:
            year(s), week(s), day(s), hour(s), minute(s), second(s), millisecond(s), microsecond(s)
        for `int`, value is assumed as `days`
        """
        if input_date is None:
            return timedelta(seconds=0)
        return parse_duration_as_timedelta(input_date)


class IgnoreOptions(BaseModel):
    exclude_audio: bool = False
    exclude_images: bool = False
    exclude_other: bool = False
    exclude_videos: bool = False
    filename_regex_filter: NonEmptyStrOrNone = None
    ignore_coomer_ads: bool = False
    only_hosts: ListNonEmptyStr = []
    skip_hosts: ListNonEmptyStr = []
    exclude_files_with_no_extension: bool = True

    @field_validator("filename_regex_filter")
    @classmethod
    def is_valid_regex(cls, value: str | None) -> str | None:
        if not value:
            return None
        try:
            re.compile(value)
        except re.error as e:
            raise ValueError("input is not a valid regex") from e
        return value


class RuntimeOptions(BaseModel):
    console_log_level: NonNegativeInt = 100
    deep_scrape: bool = False
    delete_partial_files: bool = False
    ignore_history: bool = False
    jdownloader_autostart: bool = False
    jdownloader_download_dir: PathOrNone = None
    jdownloader_whitelist: ListNonEmptyStr = []
    log_level: NonNegativeInt = DEBUG
    send_unsupported_to_jdownloader: bool = False
    skip_check_for_empty_folders: bool = False
    skip_check_for_partial_files: bool = False
    slow_download_speed: ByteSizeSerilized = ByteSize(0)
    update_last_forum_post: bool = True


class Sorting(BaseModel):
    scan_folder: PathOrNone = None
    sort_downloads: bool = False
    sort_folder: Path = DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"
    sort_incrementer_format: NonEmptyStr = " ({i})"
    sorted_audio: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Audio/{filename}{ext}"
    sorted_image: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Images/{filename}{ext}"
    sorted_other: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Other/{filename}{ext}"
    sorted_video: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Videos/{filename}{ext}"


class BrowserCookies(BaseModel):
    auto_import: bool = False
    browsers: list[BROWSERS] = [BROWSERS.chrome]
    sites: list[NonEmptyStr] = SUPPORTED_SITES_DOMAINS

    @field_validator("browsers", mode="before")
    @classmethod
    def parse_browsers(cls, values: list) -> list:
        values = parse_falsy_as(values, [])
        if isinstance(values, list):
            return sorted(str(value).lower() for value in values)
        return values

    @field_validator("sites", mode="before")
    @classmethod
    def handle_list(cls, values: list) -> list:
        values = parse_falsy_as(values, [])
        if values == ALL_SUPPORTED_SITES:
            return SUPPORTED_SITES_DOMAINS
        if isinstance(values, list):
            return sorted(str(value).lower() for value in values)
        return values

    @field_serializer("sites", when_used="json-unless-none")
    def use_placeholder(self, values: list) -> list:
        if set(values) == set(SUPPORTED_SITES_DOMAINS):
            return ALL_SUPPORTED_SITES
        return values


class DupeCleanup(BaseModel):
    add_md5_hash: bool = False
    add_sha256_hash: bool = False
    auto_dedupe: bool = True
    hashing: Hashing = Hashing.IN_PLACE
    send_deleted_to_trash: bool = True


class ConfigSettings(AliasModel):
    browser_cookies: BrowserCookies = Field(validation_alias="Browser_Cookies", default=BrowserCookies())
    download_options: DownloadOptions = Field(validation_alias="Download_Options", default=DownloadOptions())
    dupe_cleanup_options: DupeCleanup = Field(validation_alias="Dupe_Cleanup_Options", default=DupeCleanup())
    file_size_limits: FileSizeLimits = Field(validation_alias="File_Size_Limits", default=FileSizeLimits())
    media_duration_limits: MediaDurationLimits = Field(
        validation_alias="Media_Duration_Limits", default=MediaDurationLimits()
    )
    files: Files = Field(validation_alias="Files", default=Files())
    ignore_options: IgnoreOptions = Field(validation_alias="Ignore_Options", default=IgnoreOptions())
    logs: Logs = Field(validation_alias="Logs", default=Logs())
    runtime_options: RuntimeOptions = Field(validation_alias="Runtime_Options", default=RuntimeOptions())
    sorting: Sorting = Field(validation_alias="Sorting", default=Sorting())
