from pydantic import BaseModel, Field

from cyberdrop_dl.types import AliasModel


class CoomerAuth(BaseModel):
    session: str = ""


class XXXBunkerAuth(BaseModel):
    PHPSESSID: str = ""


class ImgurAuth(AliasModel):
    client_id: str = Field("", validation_alias="imgur_client_id")


class MegaNzAuth(AliasModel):
    email: str = ""
    password: str = ""


class JDownloaderAuth(AliasModel):
    username: str = Field("", validation_alias="jdownloader_username")
    password: str = Field("", validation_alias="jdownloader_password")
    device: str = Field("", validation_alias="jdownloader_device")


class KemonoAuth(AliasModel):
    session: str = ""


class RedditAuth(AliasModel):
    personal_use_script: str = Field("", validation_alias="reddit_personal_use_script")
    secret: str = Field("", validation_alias="reddit_secret")


class GoFileAuth(AliasModel):
    api_key: str = Field("", validation_alias="gofile_api_key")


class PixeldrainAuth(AliasModel):
    api_key: str = Field("", validation_alias="pixeldrain_api_key")


class RealDebridAuth(AliasModel):
    api_key: str = Field("", validation_alias="realdebrid_api_key")


class AuthSettings(AliasModel):
    coomer: CoomerAuth = Field(validation_alias="Coomer", default=CoomerAuth())
    gofile: GoFileAuth = Field(validation_alias="GoFile", default=GoFileAuth())  # type: ignore
    imgur: ImgurAuth = Field(validation_alias="Imgur", default=ImgurAuth())  # type: ignore
    jdownloader: JDownloaderAuth = Field(validation_alias="JDownloader", default=JDownloaderAuth())  # type: ignore
    kemono: KemonoAuth = Field(validation_alias="Kemono", default=KemonoAuth())  # type: ignore
    meganz: MegaNzAuth = Field(validation_alias="MegaNz", default=MegaNzAuth())  # type: ignore
    pixeldrain: PixeldrainAuth = Field(validation_alias="PixelDrain", default=PixeldrainAuth())  # type: ignore
    realdebrid: RealDebridAuth = Field(validation_alias="RealDebrid", default=RealDebridAuth())  # type: ignore
    reddit: RedditAuth = Field(validation_alias="Reddit", default=RedditAuth())  # type: ignore
    xxxbunker: XXXBunkerAuth = Field(validation_alias="XXXBunker", default=XXXBunkerAuth())  # type: ignore
