from pydantic import BaseModel, ByteSize, Field, NonNegativeFloat, PositiveInt, field_serializer

from .custom_types import AliasModel, HttpURL, NonEmptyStr


class General(BaseModel):
    allow_insecure_connections: bool = False
    user_agent: NonEmptyStr = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
    proxy: HttpURL | None = None
    flaresolverr: HttpURL | None = None
    max_file_name_length: PositiveInt = 95
    max_folder_name_length: PositiveInt = 60
    required_free_space: ByteSize = ByteSize._validate("5GB", "")

    @field_serializer("required_free_space")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)


class RateLimitingOptions(BaseModel):
    connection_timeout: PositiveInt = 15
    download_attempts: PositiveInt = 5
    read_timeout: PositiveInt = 300
    rate_limit: PositiveInt = 50
    download_delay: NonNegativeFloat = 0.5
    max_simultaneous_downloads: PositiveInt = 15
    max_simultaneous_downloads_per_domain: PositiveInt = 3
    download_speed_limit: ByteSize = ByteSize(0)

    @field_serializer("download_speed_limit")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)


class DupeCleanupOptions(BaseModel):
    delete_after_download: bool = False
    hash_while_downloading: bool = False
    keep_prev_download: bool = False
    keep_new_download: bool = True
    dedupe_already_downloaded: bool = False
    delete_off_disk: bool = False


class UIOptions(BaseModel):
    vi_mode: bool = False
    refresh_rate: PositiveInt = 10
    scraping_item_limit: PositiveInt = 5
    downloading_item_limit: PositiveInt = 5


class GlobalSettings(AliasModel):
    general: General = Field(validation_alias="General", default=General())
    rate_limiting_options: RateLimitingOptions = Field(
        validation_alias="Rate_Limiting_Options", default=RateLimitingOptions()
    )
    dupe_cleanup_options: DupeCleanupOptions = Field(
        validation_alias="Dupe_Cleanup_Options", default=DupeCleanupOptions()
    )
    ui_options: UIOptions = Field(validation_alias="UI_Options", default=UIOptions())
