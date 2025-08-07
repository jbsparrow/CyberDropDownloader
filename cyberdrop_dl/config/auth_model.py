from pydantic import BaseModel

from cyberdrop_dl.models import AliasModel

from ._common import ConfigModel, Field


class CoomerAuth(BaseModel):
    session: str = ""


class ImgurAuth(AliasModel):
    client_id: str = Field("", "imgur_client_id")


class MegaNzAuth(AliasModel):
    email: str = ""
    password: str = ""


class JDownloaderAuth(AliasModel):
    username: str = Field("", "jdownloader_username")
    password: str = Field("", "jdownloader_password")
    device: str = Field("", "jdownloader_device")


class KemonoAuth(AliasModel):
    session: str = ""


class RedditAuth(AliasModel):
    personal_use_script: str = Field("", "reddit_personal_use_script")
    secret: str = Field("", "reddit_secret")


class GoFileAuth(AliasModel):
    api_key: str = Field("", "gofile_api_key")


class PixeldrainAuth(AliasModel):
    api_key: str = Field("", "pixeldrain_api_key")


class RealDebridAuth(AliasModel):
    api_key: str = Field("", "realdebrid_api_key")


class AuthSettings(ConfigModel):
    coomer: CoomerAuth = Field(CoomerAuth(), "Coomer")
    gofile: GoFileAuth = Field(GoFileAuth(), "GoFile")
    imgur: ImgurAuth = Field(ImgurAuth(), "Imgur")
    jdownloader: JDownloaderAuth = Field(JDownloaderAuth(), "JDownloader")
    kemono: KemonoAuth = Field(KemonoAuth(), "Kemono")
    meganz: MegaNzAuth = Field(MegaNzAuth(), "MegaNz")
    pixeldrain: PixeldrainAuth = Field(PixeldrainAuth(), "PixelDrain")
    realdebrid: RealDebridAuth = Field(RealDebridAuth(), "RealDebrid")
    reddit: RedditAuth = Field(RedditAuth(), "Reddit")
