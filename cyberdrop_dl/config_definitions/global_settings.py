from datetime import timedelta

from pydantic import BaseModel, ByteSize, Field, NonNegativeFloat, PositiveInt, field_serializer, field_validator
from yarl import URL

from cyberdrop_dl.config_definitions.pydantic.validators import parse_duration_to_timedelta

from .pydantic.custom_types import AliasModel, HttpURL, NonEmptyStr

MIN_REQUIRED_FREE_SPACE = ByteSize._validate("512MB", "")
DEFAULT_REQUIRED_FREE_SPACE = ByteSize._validate("5GB", "")


def convert_to_str(value: URL | str) -> str | None:
    if not value:
        return None
    if isinstance(value, URL):
        return str(value)
    return value


class General(BaseModel):
    allow_insecure_connections: bool = False
    user_agent: NonEmptyStr = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
    proxy: HttpURL | None = None
    flaresolverr: HttpURL | None = None
    max_file_name_length: PositiveInt = 95
    max_folder_name_length: PositiveInt = 60
    required_free_space: ByteSize = DEFAULT_REQUIRED_FREE_SPACE

    @field_serializer("required_free_space")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)

    @field_serializer("flaresolverr", "proxy")
    def serialize(self, value: URL | str) -> str | None:
        return convert_to_str(value)

    @field_validator("flaresolverr", "proxy", mode="before")
    @classmethod
    def convert_to_str(cls, value: URL | str) -> str | None:
        return convert_to_str(value)

    @field_validator("required_free_space", mode="after")
    @classmethod
    def override_min(cls, value: ByteSize) -> ByteSize:
        return max(value, MIN_REQUIRED_FREE_SPACE)


class RateLimitingOptions(BaseModel):
    connection_timeout: PositiveInt = 15
    download_attempts: PositiveInt = 5
    read_timeout: PositiveInt = 300
    rate_limit: PositiveInt = 50
    download_delay: NonNegativeFloat = 0.5
    max_simultaneous_downloads: PositiveInt = 15
    max_simultaneous_downloads_per_domain: PositiveInt = 3
    download_speed_limit: ByteSize = ByteSize(0)
    file_host_cache_expire_after: timedelta = timedelta(days=7)
    forum_cache_expire_after: timedelta = timedelta(weeks=4)

    @field_serializer("download_speed_limit")
    def human_readable(self, value: ByteSize | int) -> str:
        if not isinstance(value, ByteSize):
            value = ByteSize(value)
        return value.human_readable(decimal=True)

    @field_validator("file_host_cache_expire_after", "forum_cache_expire_after", mode="before")
    @staticmethod
    def parse_cache_duration(input_date: timedelta | str | int) -> timedelta:
        """Parses `datetime.timedelta`, `str` or `int` into a timedelta format.

        for `str`, the expected format is `value unit`, ex: `5 days`, `10 minutes`, `1 year`

        valid units:
            year(s), week(s), day(s), hour(s), minute(s), second(s), millisecond(s), microsecond(s)

        for `int`, value is assummed as `days`
        """
        return parse_duration_to_timedelta(input_date)


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
    ui_options: UIOptions = Field(validation_alias="UI_Options", default=UIOptions())
