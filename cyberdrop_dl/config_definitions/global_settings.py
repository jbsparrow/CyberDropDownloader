from typing import Annotated

from pydantic import BaseModel, NonNegativeInt, PositiveFloat, PositiveInt, StringConstraints
from yarl import URL

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class General(BaseModel):
    allow_insecure_connections: bool
    user_agent: NonEmptyStr
    proxy: URL | None
    flaresolverr: URL | None
    max_file_name_length: PositiveInt
    max_folder_name_length: PositiveInt
    required_free_space: PositiveInt


class RateLimitingOptions(BaseModel):
    connection_timeout: PositiveInt
    download_attempts: PositiveInt
    read_timeout: PositiveInt
    rate_limit: PositiveInt
    download_delay: PositiveFloat
    max_simultaneous_downloads: PositiveInt
    max_simultaneous_downloads_per_domain: PositiveInt
    download_speed_limit: NonNegativeInt


class DupeCleanupOptions(BaseModel):
    delete_after_download: bool
    hash_while_downloading: bool
    keep_prev_download: bool
    keep_new_download: bool
    dedupe_already_downloaded: bool
    delete_off_disk: bool


class UIOptions(BaseModel):
    vi_mode: bool
    refresh_rate: PositiveInt
    scraping_item_limit: PositiveInt
    downloading_item_limit: PositiveInt


class GlobalSettings(BaseModel):
    general: General
    rate_limiting_options: RateLimitingOptions
    dupe_cleanup_options: DupeCleanupOptions
    ui_options: UIOptions
