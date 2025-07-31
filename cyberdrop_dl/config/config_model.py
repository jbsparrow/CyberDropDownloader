import itertools
import re
from datetime import datetime, timedelta
from logging import DEBUG
from pathlib import Path

from pydantic import BaseModel, ByteSize, NonNegativeInt, PositiveInt, field_serializer, field_validator

from cyberdrop_dl import constants
from cyberdrop_dl.constants import BROWSERS, DEFAULT_APP_STORAGE, DEFAULT_DOWNLOAD_STORAGE
from cyberdrop_dl.data_structures.hash import Hashing
from cyberdrop_dl.data_structures.supported_domains import SUPPORTED_SITES_DOMAINS
from cyberdrop_dl.models import HttpAppriseURL
from cyberdrop_dl.models.types import (
    ByteSizeSerilized,
    ListNonEmptyStr,
    ListNonNegativeInt,
    LogPath,
    MainLogPath,
    NonEmptyStr,
    NonEmptyStrOrNone,
    PathOrNone,
)
from cyberdrop_dl.models.validators import falsy_as, to_timedelta
from cyberdrop_dl.utils.strings import validate_format_string
from cyberdrop_dl.utils.utilities import purge_dir_tree

from ._common import ConfigModel, Field, PathAliasModel

ALL_SUPPORTED_SITES = ["<<ALL_SUPPORTED_SITES>>"]
_SORTING_COMMON_FIELDS = {
    "base_dir",
    "ext",
    "file_date",
    "file_date_iso",
    "file_date_us",
    "filename",
    "parent_dir",
    "sort_dir",
}


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

    @field_validator("separate_posts_format", mode="after")
    @classmethod
    def valid_format(cls, value: str) -> str:
        valid_keys = {"default", "title", "id", "number", "date"}
        validate_format_string(value, valid_keys)
        return value


class Files(PathAliasModel):
    download_folder: Path = Field(DEFAULT_DOWNLOAD_STORAGE, "d")
    dump_json: bool = Field(False, "j")
    input_file: Path = Field(DEFAULT_APP_STORAGE / "Configs{config}/URLs.txt", "i")
    save_pages_html: bool = False


class Logs(PathAliasModel):
    download_error_urls: LogPath = Field(Path("Download_Error_URLs.csv"), "download_error_urls_filename")
    last_forum_post: LogPath = Field(Path("Last_Scraped_Forum_Posts.csv"), "last_forum_post_filename")
    log_folder: Path = DEFAULT_APP_STORAGE / "Configs/{config}/Logs"
    log_line_width: PositiveInt = Field(240, ge=50)
    logs_expire_after: timedelta | None = None
    main_log: MainLogPath = Field(Path("downloader.log"), "main_log_filename")
    rotate_logs: bool = False
    scrape_error_urls: LogPath = Field(Path("Scrape_Error_URLs.csv"), "scrape_error_urls_filename")
    unsupported_urls: LogPath = Field(Path("Unsupported_URLs.csv"), "unsupported_urls_filename")
    webhook: HttpAppriseURL | None = Field(None, "webhook_url")

    @property
    def cdl_responses_dir(self) -> Path:
        return self.main_log.parent / "cdl_responses"

    @field_validator("webhook", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        return falsy_as(value, None)

    @field_validator("logs_expire_after", mode="before")
    @staticmethod
    def parse_logs_duration(input_date: timedelta | str | int | None) -> timedelta | str | None:
        if value := falsy_as(input_date, None):
            return to_timedelta(value)

    def _set_output_filenames(self, now: datetime) -> None:
        self.log_folder.mkdir(exist_ok=True, parents=True)
        current_time_file_iso: str = now.strftime(constants.LOGS_DATETIME_FORMAT)
        current_time_folder_iso: str = now.strftime(constants.LOGS_DATE_FORMAT)
        for attr, log_file in vars(self).items():
            if not isinstance(log_file, Path) or log_file.suffix not in (".csv", ".log"):
                continue

            if self.rotate_logs:
                new_name = f"{log_file.stem}_{current_time_file_iso}{log_file.suffix}"
                log_file: Path = log_file.parent / current_time_folder_iso / new_name
                setattr(self, attr, self.log_folder / log_file)

            log_file.parent.mkdir(exist_ok=True, parents=True)

    def _delete_old_logs_and_folders(self, now: datetime | None = None) -> None:
        if now and self.logs_expire_after:
            for file in itertools.chain(self.log_folder.rglob("*.log"), self.log_folder.rglob("*.csv")):
                file_date = file.stat().st_ctime
                t_delta = now - datetime.fromtimestamp(file_date)
                if t_delta > self.logs_expire_after:
                    file.unlink(missing_ok=True)
        purge_dir_tree(self.log_folder)


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
    def parse_runtime_duration(input_date: timedelta | str | int | None) -> timedelta | str:
        """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.
        for `str`, the expected format is `value unit`, ex: `5 days`, `10 minutes`, `1 year`
        valid units:
            year(s), week(s), day(s), hour(s), minute(s), second(s), millisecond(s), microsecond(s)
        for `int`, value is assumed as `days`
        """
        if input_date is None:
            return timedelta(seconds=0)
        return to_timedelta(input_date)


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
    sort_folder: Path = DEFAULT_DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"
    sort_incrementer_format: NonEmptyStr = " ({i})"
    sorted_audio: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Audio/{filename}{ext}"
    sorted_image: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Images/{filename}{ext}"
    sorted_other: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Other/{filename}{ext}"
    sorted_video: NonEmptyStrOrNone = "{sort_dir}/{base_dir}/Videos/{filename}{ext}"

    @field_validator("sort_incrementer_format", mode="after")
    @classmethod
    def valid_sort_incrementer_format(cls, value: str | None) -> str | None:
        if value is not None:
            valid_keys = {"i"}
            validate_format_string(value, valid_keys)
        return value

    @field_validator("sorted_audio", mode="after")
    @classmethod
    def valid_sorted_audio(cls, value: str | None) -> str | None:
        if value is not None:
            valid_keys = _SORTING_COMMON_FIELDS | {"bitrate", "duration", "length", "sample_rate"}
            validate_format_string(value, valid_keys)
        return value

    @field_validator("sorted_image", mode="after")
    @classmethod
    def valid_sorted_image(cls, value: str | None) -> str | None:
        if value is not None:
            valid_keys = _SORTING_COMMON_FIELDS | {"height", "resolution", "width"}
            validate_format_string(value, valid_keys)
        return value

    @field_validator("sorted_other", mode="after")
    @classmethod
    def valid_sorted_other(cls, value: str | None) -> str | None:
        if value is not None:
            valid_keys = _SORTING_COMMON_FIELDS | {"bitrate", "duration", "length", "sample_rate"}
            validate_format_string(value, valid_keys)
        return value

    @field_validator("sorted_video", mode="after")
    @classmethod
    def valid_sorted_video(cls, value: str | None) -> str | None:
        if value is not None:
            valid_keys = _SORTING_COMMON_FIELDS | {
                "codec",
                "duration",
                "fps",
                "height",
                "length",
                "resolution",
                "width",
            }
            validate_format_string(value, valid_keys)
        return value


class BrowserCookies(BaseModel):
    auto_import: bool = False
    browser: BROWSERS | None = BROWSERS.firefox
    sites: list[NonEmptyStr] = SUPPORTED_SITES_DOMAINS

    def model_post_init(self, *_) -> None:
        if self.auto_import and not self.browser:
            raise ValueError("You need to provide a browser for auto_import to work")

    @field_validator("sites", mode="before")
    @classmethod
    def handle_list(cls, values: list) -> list:
        values = falsy_as(values, [])
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


class ConfigSettings(ConfigModel):
    browser_cookies: BrowserCookies = Field(BrowserCookies(), "Browser_Cookies")
    download_options: DownloadOptions = Field(DownloadOptions(), "Download_Options")
    dupe_cleanup_options: DupeCleanup = Field(DupeCleanup(), "Dupe_Cleanup_Options")
    file_size_limits: FileSizeLimits = Field(FileSizeLimits(), "File_Size_Limits")
    media_duration_limits: MediaDurationLimits = Field(MediaDurationLimits(), "Media_Duration_Limits")
    files: Files = Field(Files(), "Files")
    ignore_options: IgnoreOptions = Field(IgnoreOptions(), "Ignore_Options")
    logs: Logs = Field(Logs(), "Logs")
    runtime_options: RuntimeOptions = Field(RuntimeOptions(), "Runtime_Options")
    sorting: Sorting = Field(Sorting(), "Sorting")
