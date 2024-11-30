from logging import DEBUG
from pathlib import Path

from pydantic import BaseModel, ByteSize, Field, NonNegativeInt, PositiveInt, field_serializer, field_validator

from cyberdrop_dl import __version__ as current_version
from cyberdrop_dl.utils.constants import APP_STORAGE, BROWSERS, DOWNLOAD_STORAGE, PRERELEASE_TAGS
from cyberdrop_dl.utils.data_enums_classes.hash import Hashing

from .custom_types import AliasModel, HttpAppriseURLModel, NonEmptyStr

if next((tag for tag in PRERELEASE_TAGS if tag in current_version), False):
    from cyberdrop_dl.utils.data_enums_classes.supported_domains import SupportedSitesDebug as SupportedSites
else:
    from cyberdrop_dl.utils.data_enums_classes.supported_domains import SupportedSites


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
    webhook: HttpAppriseURLModel | None = Field(validation_alias="webhook_url", default=None)
    main_log_filename: Path = Path("downloader.log")
    last_forum_post_filename: Path = Path("Last_Scraped_Forum_Posts.csv")
    unsupported_urls_filename: Path = Path("Unsupported_URLs.csv")
    download_error_urls_filename: Path = Path("Download_Error_URLs.csv")
    scrape_error_urls_filename: Path = Path("Scrape_Error_URLs.csv")
    rotate_logs: bool = False
    log_line_width: PositiveInt = Field(default=240, ge=50)

    @field_validator("webhook", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value:
            return None
        return value

    @field_validator("webhook", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value:
            return None
        return value


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

    @field_validator("skip_hosts", "only_hosts", mode="before")
    @classmethod
    def handle_falsy(cls, value: list) -> list:
        if not value:
            return []
        return value


class RuntimeOptions(BaseModel):
    ignore_history: bool = False
    log_level: int = DEBUG
    console_log_level: int = 100
    skip_check_for_partial_files: bool = False
    skip_check_for_empty_folders: bool = False
    delete_partial_files: bool = False
    update_last_forum_post: bool = True
    send_unsupported_to_jdownloader: bool = False
    jdownloader_download_dir: Path | None = None
    jdownloader_autostart: bool = False
    jdownloader_whitelist: list[NonEmptyStr] = []

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

    @field_validator("scan_folder", mode="before")
    @classmethod
    def handle_falsy(cls, value: str) -> str | None:
        if not value or value == "None":
            return None
        return value


class BrowserCookies(BaseModel):
    browsers: list[BROWSERS] = [BROWSERS.chrome]
    auto_import: bool = False
    sites: list[SupportedSites] = [domain.value for domain in SupportedSites]

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
