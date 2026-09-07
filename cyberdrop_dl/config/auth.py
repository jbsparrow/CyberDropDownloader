from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, override

from cyclopts import Parameter
from pydantic import Field, Secret

from cyberdrop_dl.models import AppriseURL, ConfigModel
from cyberdrop_dl.models.types import FalsyAsNone  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


def _censor(value: object) -> object:
    if value and isinstance(value, str):
        return Secret(value)
    return value


@Parameter(show=False)
class CensoredModel(ConfigModel):
    @override
    def __repr_name__(self) -> str:
        return ""

    @override
    def __repr__(self) -> str:
        return f"{{{self.__repr_str__(', ')}}}"

    @override
    def __repr_args__(self) -> Iterable[tuple[str | None, Any]]:
        for name, value in super().__repr_args__():
            yield name, _censor(value)


class ApiKeyAuth(CensoredModel):
    api_key: str | None = None


class EmailAuth(CensoredModel):
    email: str | None = None
    password: str | None = None


class JDownloaderAuth(CensoredModel):
    email: str | None = Field(validation_alias="username", default=None)
    password: str | None = None
    device_name: str | None = Field(validation_alias="device", default=None)


class Notifications(CensoredModel):
    apprise: tuple[AppriseURL, ...] = ()
    webhook: FalsyAsNone[AppriseURL] = None

    @override
    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        if not self.apprise:
            return

        import importlib.util

        if not importlib.util.find_spec("apprise"):
            logger.warning("Found apprise URLs for notifications but apprise is not installed. Ignoring")
            self.apprise = ()


@Parameter(show=False)
class Authentication(ConfigModel):
    gofile: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
    jdownloader: JDownloaderAuth = Field(default_factory=JDownloaderAuth)
    mega_nz: EmailAuth = Field(default_factory=EmailAuth)
    pixeldrain: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
    nova: ApiKeyAuth = Field(default_factory=ApiKeyAuth)
    real_debrid: ApiKeyAuth = Field(default_factory=ApiKeyAuth)

    def censored_dump(self) -> dict[str, bool]:
        return {site: all(vars(credentials).values()) for site, credentials in self}
