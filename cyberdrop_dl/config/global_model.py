import random
from datetime import timedelta
from typing import Literal, NamedTuple

import aiohttp
from pydantic import BaseModel, ByteSize, NonNegativeFloat, PositiveInt, field_serializer, field_validator
from yarl import URL

from cyberdrop_dl.config._common import ConfigModel, Field
from cyberdrop_dl.models.types import ByteSizeSerilized, HttpURL, ListNonEmptyStr, ListPydanticURL, NonEmptyStr
from cyberdrop_dl.models.validators import falsy_as, to_bytesize, to_timedelta

MIN_REQUIRED_FREE_SPACE = to_bytesize("512MB")
DEFAULT_REQUIRED_FREE_SPACE = to_bytesize("5GB")


class Timeout(NamedTuple):
    connect: int
    read: int

    @property
    def total(self) -> int:
        return self.read + self.connect


class General(BaseModel):
    # TODO: Move `ssl_context` to an advance config section
    ssl_context: Literal["truststore", "certifi", "truststore+certifi"] | None = "truststore+certifi"
    disable_crawlers: ListNonEmptyStr = []
    enable_generic_crawler: bool = True
    flaresolverr: HttpURL | None = None
    max_file_name_length: PositiveInt = 95
    max_folder_name_length: PositiveInt = 60
    proxy: HttpURL | None = None
    required_free_space: ByteSizeSerilized = DEFAULT_REQUIRED_FREE_SPACE
    user_agent: NonEmptyStr = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"

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

    def model_post_init(self, *_) -> None:
        self._timeout = Timeout(self.connection_timeout, self.read_timeout)
        self._scrape_timeout = aiohttp.ClientTimeout(total=self._timeout.total, connect=self._timeout.connect)
        self._download_timeout = aiohttp.ClientTimeout(total=None, connect=self._timeout.connect)

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
    downloading_item_limit: PositiveInt = 5
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
