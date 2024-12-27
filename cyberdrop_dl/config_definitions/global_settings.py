import re
from datetime import timedelta

from pydantic import BaseModel, ByteSize, Field, NonNegativeFloat, PositiveInt, field_serializer, field_validator
from yarl import URL

from .custom_types import AliasModel, HttpURL, NonEmptyStr

DATE_PATTERN = re.compile(
    r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)", re.IGNORECASE
)
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
    required_free_space: ByteSize = Field(DEFAULT_REQUIRED_FREE_SPACE, gt=MIN_REQUIRED_FREE_SPACE)

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
        if not input_date:
            return 0
        parsed_timedelta = input_date
        if isinstance(input_date, int):
            parsed_timedelta = timedelta(days=input_date)
        if isinstance(input_date, str):
            time_str = input_date.casefold()
            matches: list[str] = re.findall(DATE_PATTERN, time_str)
            seen_units = set()
            time_dict = {"days": 0}

            for value, unit in matches:
                value = int(value)
                unit = unit.lower()
                normalized_unit = unit.rstrip("s")
                plural_unit = normalized_unit + "s"
                if normalized_unit in seen_units:
                    raise ValueError(f"Duplicate time unit detected: '{unit}' conflicts with another entry.")
                seen_units.add(normalized_unit)

                if "day" in unit:
                    time_dict["days"] += value
                elif "month" in unit:
                    time_dict["days"] += value * 30
                elif "year" in unit:
                    time_dict["days"] += value * 365
                else:
                    time_dict[plural_unit] = value

            if matches:
                parsed_timedelta = timedelta(**time_dict)

        return parsed_timedelta


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
