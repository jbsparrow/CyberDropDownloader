import random
from datetime import timedelta

from pydantic import BaseModel, ByteSize, Field, NonNegativeFloat, PositiveInt, field_serializer, field_validator
from yarl import URL

from cyberdrop_dl.types import AliasModel, ByteSizeSerilized, HttpURL, NonEmptyStr
from cyberdrop_dl.utils.converters import convert_to_byte_size
from cyberdrop_dl.utils.validators import parse_duration_as_timedelta, parse_falsy_as

MIN_REQUIRED_FREE_SPACE = convert_to_byte_size("512MB")
DEFAULT_REQUIRED_FREE_SPACE = convert_to_byte_size("5GB")


class General(BaseModel):
    allow_insecure_connections: bool = False
    enable_generic_crawler: bool = True
    flaresolverr: HttpURL | None = None
    max_file_name_length: PositiveInt = 95
    max_folder_name_length: PositiveInt = 60
    proxy: HttpURL | None = None
    required_free_space: ByteSizeSerilized = DEFAULT_REQUIRED_FREE_SPACE
    user_agent: NonEmptyStr = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
    pause_on_insufficient_space: bool = False

    @field_serializer("flaresolverr", "proxy")
    def serialize(self, value: URL | str) -> str | None:
        return parse_falsy_as(value, None, str)

    @field_validator("flaresolverr", "proxy", mode="before")
    @classmethod
    def convert_to_str(cls, value: URL | str) -> str | None:
        return parse_falsy_as(value, None, str)

    @field_validator("required_free_space", mode="after")
    @classmethod
    def override_min(cls, value: ByteSize) -> ByteSize:
        return max(value, MIN_REQUIRED_FREE_SPACE)


class RateLimiting(BaseModel):
    connection_timeout: PositiveInt = 15
    download_attempts: PositiveInt = 5
    download_delay: NonNegativeFloat = 0.5
    download_speed_limit: ByteSizeSerilized = ByteSize(0)
    file_host_cache_expire_after: timedelta = timedelta(days=7)
    forum_cache_expire_after: timedelta = timedelta(weeks=4)
    jitter: NonNegativeFloat = 0
    max_simultaneous_downloads_per_domain: PositiveInt = 3
    max_simultaneous_downloads: PositiveInt = 15
    rate_limit: PositiveInt = 50
    read_timeout: PositiveInt = 300

    @field_validator("file_host_cache_expire_after", "forum_cache_expire_after", mode="before")
    @staticmethod
    def parse_cache_duration(input_date: timedelta | str | int) -> timedelta:
        return parse_duration_as_timedelta(input_date)

    @property
    def total_delay(self) -> NonNegativeFloat:
        """download_delay + jitter"""
        return self.download_delay + self.get_jitter()

    def get_jitter(self) -> NonNegativeFloat:
        """Get a random number in the range [0, self.jitter]"""
        return random.uniform(0, self.jitter)


class UIOptions(BaseModel):
    downloading_item_limit: PositiveInt = 5
    refresh_rate: PositiveInt = 10
    scraping_item_limit: PositiveInt = 5
    vi_mode: bool = False


class GlobalSettings(AliasModel):
    general: General = Field(validation_alias="General", default=General())
    rate_limiting_options: RateLimiting = Field(validation_alias="Rate_Limiting_Options", default=RateLimiting())
    ui_options: UIOptions = Field(validation_alias="UI_Options", default=UIOptions())
