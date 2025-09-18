import random
from datetime import timedelta
from typing import Literal

import aiohttp
from pydantic import (
    BaseModel,
    ByteSize,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    field_serializer,
    field_validator,
)
from yarl import URL

from cyberdrop_dl.config._common import ConfigModel, Field
from cyberdrop_dl.models.types import ByteSizeSerilized, HttpURL, ListNonEmptyStr, ListPydanticURL, NonEmptyStr
from cyberdrop_dl.models.validators import falsy_as, falsy_as_none, to_bytesize, to_timedelta

MIN_REQUIRED_FREE_SPACE = to_bytesize("512MB")
DEFAULT_REQUIRED_FREE_SPACE = to_bytesize("5GB")


class General(BaseModel):
    # TODO: Move `ssl_context` to an advance config section
    ssl_context: Literal["truststore", "certifi", "truststore+certifi"] | None = "truststore+certifi"
    disable_crawlers: ListNonEmptyStr = []
    enable_generic_crawler: bool = False
    flaresolverr: HttpURL | None = None
    max_file_name_length: PositiveInt = 95
    max_folder_name_length: PositiveInt = 60
    proxy: HttpURL | None = None
    required_free_space: ByteSizeSerilized = DEFAULT_REQUIRED_FREE_SPACE
    user_agent: NonEmptyStr = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0"

    @field_validator("ssl_context", mode="before")
    @classmethod
    def ssl(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            value = value.lower().strip()
        return falsy_as(value, None)

    @field_validator("disable_crawlers", mode="after")
    @classmethod
    def unique_list(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @field_serializer("flaresolverr", "proxy")
    def serialize(self, value: URL | str) -> str | None:
        return falsy_as(value, None, str)

    @field_validator("flaresolverr", "proxy", mode="before")
    @classmethod
    def convert_to_str(cls, value: str) -> str | None:
        return falsy_as(value, None, str)

    @field_validator("required_free_space", mode="after")
    @classmethod
    def override_min(cls, value: ByteSize) -> ByteSize:
        return max(value, MIN_REQUIRED_FREE_SPACE)


class RateLimiting(BaseModel):
    download_attempts: PositiveInt = 2
    download_delay: NonNegativeFloat = 0.0
    download_speed_limit: ByteSizeSerilized = ByteSize(0)
    file_host_cache_expire_after: timedelta = timedelta(days=7)
    forum_cache_expire_after: timedelta = timedelta(weeks=4)
    jitter: NonNegativeFloat = 0
    max_simultaneous_downloads_per_domain: PositiveInt = 5
    max_simultaneous_downloads: PositiveInt = 15
    rate_limit: PositiveInt = 50

    connection_timeout: PositiveFloat = 15
    read_timeout: PositiveFloat | None = 300

    @field_validator("read_timeout", mode="before")
    @classmethod
    def parse_timeouts(cls, value: object) -> object | None:
        return falsy_as_none(value)

    def model_post_init(self, *_) -> None:
        self._curl_timeout = self.connection_timeout
        if self.read_timeout is not None:
            self._curl_timeout = self.connection_timeout, self.read_timeout
        self._aiohttp_timeout = aiohttp.ClientTimeout(
            total=None,
            sock_connect=self.connection_timeout,
            sock_read=self.read_timeout,
        )

    @field_validator("file_host_cache_expire_after", "forum_cache_expire_after", mode="before")
    @staticmethod
    def parse_cache_duration(input_date: timedelta | str | int) -> timedelta | str:
        return to_timedelta(input_date)

    @property
    def total_delay(self) -> NonNegativeFloat:
        """download_delay + jitter"""
        return self.download_delay + self.get_jitter()

    def get_jitter(self) -> NonNegativeFloat:
        """Get a random number in the range [0, self.jitter]"""
        return random.uniform(0, self.jitter)


class UIOptions(BaseModel):
    downloading_item_limit: PositiveInt = 10
    refresh_rate: PositiveInt = 10
    scraping_item_limit: PositiveInt = 5
    vi_mode: bool = False


class GenericCrawlerInstances(BaseModel):
    wordpress_media: ListPydanticURL = []
    wordpress_html: ListPydanticURL = []
    discourse: ListPydanticURL = []
    chevereto: ListPydanticURL = []


class GlobalSettings(ConfigModel):
    general: General = Field(General(), "General")
    rate_limiting_options: RateLimiting = Field(RateLimiting(), "Rate_Limiting_Options")
    ui_options: UIOptions = Field(UIOptions(), "UI_Options")
    generic_crawlers_instances: GenericCrawlerInstances = GenericCrawlerInstances()
