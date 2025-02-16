from datetime import timedelta
from logging import DEBUG
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ByteSize, Field, NonNegativeInt, PositiveInt, field_serializer, field_validator

from cyberdrop_dl.config_definitions.pydantic.validators import parse_duration_to_timedelta
from cyberdrop_dl.utils.constants import APP_STORAGE, BROWSERS, DOWNLOAD_STORAGE
from cyberdrop_dl.utils.data_enums_classes.hash import Hashing
from cyberdrop_dl.utils.data_enums_classes.supported_domains import SUPPORTED_SITES_DOMAINS

from .pydantic.custom_types import AliasModel, HttpAppriseURL, NonEmptyStr


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
    separate_posts_format: NonEmptyStr = "{default}"
    skip_download_mark_completed: bool = False
    skip_referer_seen_before: bool = False
    maximum_number_of_children: list[NonNegativeInt] = []
    maximum_thread_depth: NonNegativeInt = 0

    @field_validator("maximum_number_of_children", mode="before")
    @classmethod
    def handle_falsy(cls, value: list) -> list:
        if not value:
            return []
        return value


class Files(AliasModel):
    input_file: Path = Field(validation_alias="i", default=APP_STORAGE / "Configs" / "{config}" / "URLs.txt")
    download_folder: Path = Field(validation_alias="d", default=DOWNLOAD_STORAGE)


class Logs(AliasModel):
    log_folder: Path = APP_STORAGE / "Configs" / "{config}" / "Logs"
    webhook: HttpAppriseURL | None = Field(validation_alias="webhook_url", default=None)
    main_log: Path = Field(Path("downloader.log"), validation_alias="main_log_filename")
    last_forum_post: Path = Field(Path("Last_Scraped_Forum_Posts.csv"), validation_alias="last_forum_post_filename")
    unsupported_urls: Path = Field(Path("Unsupported_URLs.csv"), validation_alias="unsupported_urls_filename")
    download_error_urls: Path = Field(Path("Download_Error_URLs.csv"), validation_alias="download_error_urls_filename")
    scrape_error_urls: Path = Field(Path("Scrape_Error_URLs.csv"), validation_alias="scrape_error_urls_filename")
    rotate_logs: bool = False
    log_line_width: PositiveInt = Field(default=240, ge=50)
    logs_expire_after: timedelta | None = None

    @field_validator("webhook", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value:
            return None
        return value

    @field_validator("main_log", mode="after")
    @classmethod
    def fix_main_log_extension(cls, value: Path) -> Path:
        return value.with_suffix(".log")

    @field_validator("last_forum_post", "unsupported_urls", "download_error_urls", "scrape_error_urls", mode="after")
    @classmethod
    def fix_other_logs_extensions(cls, value: Path) -> Path:
        return value.with_suffix(".csv")

    @field_validator("logs_expire_after", mode="before")
    @staticmethod
    def parse_logs_duration(input_date: timedelta | str | int | None) -> timedelta:
        """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.

        for `str`, the expected format is `value unit`, ex: `5 days`, `10 minutes`, `1 year`

        valid units:
            year(s), week(s), day(s), hour(s), minute(s), second(s), millisecond(s), microsecond(s)

        for `int`, value is assumed as `days`
        """
        if input_date is None:
            return None
        return parse_duration_to_timedelta(input_date)


class FileSizeLimits(BaseModel):
    maximum_image_size: ByteSize = ByteSize(0)
    maximum_other_size: ByteSize = ByteSize(0)
    maximum_video_size: ByteSize = ByteSize(0)
    minimum_image_size: ByteSize = ByteSize(0)
    minimum_other_size: ByteSize = ByteSize(0)
    minimum_video_size: ByteSize = ByteSize(0)

    @field_serializer("*")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)


class IgnoreOptions(BaseModel):
    exclude_videos: bool = False
    exclude_images: bool = False
    exclude_audio: bool = False
    exclude_other: bool = False
    ignore_coomer_ads: bool = False
    skip_hosts: list[NonEmptyStr] = []
    only_hosts: list[NonEmptyStr] = []
    filename_regex_filter: NonEmptyStr | None = None
    exclude_files_with_no_extension: bool = True

    @field_validator("skip_hosts", "only_hosts", mode="before")
    @classmethod
    def handle_falsy(cls, value: list) -> list:
        if not value:
            return []
        return value


class RuntimeOptions(BaseModel):
    ignore_history: bool = False
    log_level: NonNegativeInt = DEBUG
    console_log_level: NonNegativeInt = 100
    skip_check_for_partial_files: bool = False
    skip_check_for_empty_folders: bool = False
    delete_partial_files: bool = False
    update_last_forum_post: bool = True
    send_unsupported_to_jdownloader: bool = False
    jdownloader_download_dir: Path | None = None
    jdownloader_autostart: bool = False
    jdownloader_whitelist: list[NonEmptyStr] = []
    deep_scrape: bool = False
    slow_download_speed: ByteSize = ByteSize(0)

    @field_validator("jdownloader_download_dir", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value or value == "None":
            return None
        return value

    @field_validator("jdownloader_whitelist", mode="before")
    @classmethod
    def handle_list(cls, value: list) -> list:
        if not value:
            return []
        return value

    @field_serializer("slow_download_speed")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)


# TODO: allow None values in sorting format to skip that type of file
class Sorting(BaseModel):
    sort_downloads: bool = False
    sort_folder: Path = DOWNLOAD_STORAGE / "Cyberdrop-DL Sorted Downloads"
    scan_folder: Path | None = None
    sort_incrementer_format: NonEmptyStr = " ({i})"
    sorted_audio: NonEmptyStr | None = "{sort_dir}/{base_dir}/Audio/{filename}{ext}"
    sorted_image: NonEmptyStr | None = "{sort_dir}/{base_dir}/Images/{filename}{ext}"
    sorted_other: NonEmptyStr | None = "{sort_dir}/{base_dir}/Other/{filename}{ext}"
    sorted_video: NonEmptyStr | None = "{sort_dir}/{base_dir}/Videos/{filename}{ext}"

    @field_validator("scan_folder", "sorted_audio", "sorted_image", "sorted_other", "sorted_video", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value or value == "None":
            return None
        return value


class BrowserCookies(BaseModel):
    browsers: list[BROWSERS] = [BROWSERS.chrome]
    auto_import: bool = False
    sites: list[Literal[*SUPPORTED_SITES_DOMAINS]] = SUPPORTED_SITES_DOMAINS  # type: ignore

    @field_validator("browsers", "sites", mode="before")
    @classmethod
    def handle_list(cls, values: list) -> list:
        if not values:
            return []
        if isinstance(values, list):
            return [str(value).lower() for value in values]
        return values


class DupeCleanupOptions(BaseModel):
    hashing: Hashing = Hashing.IN_PLACE
    auto_dedupe: bool = True
    add_md5_hash: bool = False
    add_sha256_hash: bool = False
    send_deleted_to_trash: bool = True


class ConfigSettings(AliasModel):
    browser_cookies: BrowserCookies = Field(validation_alias="Browser_Cookies", default=BrowserCookies())
    download_options: DownloadOptions = Field(validation_alias="Download_Options", default=DownloadOptions())
    dupe_cleanup_options: DupeCleanupOptions = Field(
        validation_alias="Dupe_Cleanup_Options", default=DupeCleanupOptions()
    )
    file_size_limits: FileSizeLimits = Field(validation_alias="File_Size_Limits", default=FileSizeLimits())
    files: Files = Field(validation_alias="Files", default=Files())
    ignore_options: IgnoreOptions = Field(validation_alias="Ignore_Options", default=IgnoreOptions())
    logs: Logs = Field(validation_alias="Logs", default=Logs())
    runtime_options: RuntimeOptions = Field(validation_alias="Runtime_Options", default=RuntimeOptions())
    sorting: Sorting = Field(validation_alias="Sorting", default=Sorting())
