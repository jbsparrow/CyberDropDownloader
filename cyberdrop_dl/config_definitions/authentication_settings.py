from pydantic import BaseModel, Field, SecretStr

from .custom_types import AliasModel


class ForumAuth(BaseModel):
    celebforum_xf_user_cookie: SecretStr = ""
    celebforum_username: SecretStr = ""
    celebforum_password: SecretStr = ""
    f95zone_xf_user_cookie: SecretStr = ""
    f95zone_username: SecretStr = ""
    f95zone_password: SecretStr = ""
    leakedmodels_xf_user_cookie: SecretStr = ""
    leakedmodels_username: SecretStr = ""
    leakedmodels_password: SecretStr = ""
    nudostar_xf_user_cookie: SecretStr = ""
    nudostar_username: SecretStr = ""
    nudostar_password: SecretStr = ""
    simpcity_xf_user_cookie: SecretStr = ""
    simpcity_username: SecretStr = ""
    simpcity_password: SecretStr = ""
    socialmediagirls_xf_user_cookie: SecretStr = ""
    socialmediagirls_username: SecretStr = ""
    socialmediagirls_password: SecretStr = ""
    xbunker_xf_user_cookie: SecretStr = ""
    xbunker_username: SecretStr = ""
    xbunker_password: SecretStr = ""


class CoomerAuth(BaseModel):
    session: SecretStr = ""


class XXXBunkerAuth(BaseModel):
    PHPSESSID: SecretStr = ""


class ImgurAuth(BaseModel):
    client_id: SecretStr = ""


class JDownloaderAuth(AliasModel):
    username: SecretStr = Field("", validation_alias="jdownloader_username")
    password: SecretStr = Field("", validation_alias="jdownloader_password")
    device: SecretStr = Field("", validation_alias="jdownloader_device")


class RedditAuth(BaseModel):
    personal_use_script: SecretStr = ""
    secret: SecretStr = ""


class GoFileAuth(AliasModel):
    api_key: SecretStr = Field("", validation_alias="gofile_api_key")


class PixeldrainAuth(AliasModel):
    api_key: SecretStr = Field("", validation_alias="pixeldrain_api_key")


class RealDebridAuth(AliasModel):
    api_key: SecretStr = Field("", validation_alias="realdebrid_api_key")


class AuthSettings(AliasModel):
    coomer: CoomerAuth = Field(validation_alias="Coomer", default=CoomerAuth())
    forums: ForumAuth = Field(validation_alias="Forums", default=ForumAuth())
    gofile: GoFileAuth = Field(validation_alias="GoFile", default=GoFileAuth())
    imgur: ImgurAuth = Field(validation_alias="Imgur", default=ImgurAuth())
    jdownloader: JDownloaderAuth = Field(validation_alias="JDownloader", default=JDownloaderAuth())
    pixeldrain: PixeldrainAuth = Field(validation_alias="PixelDrain", default=PixeldrainAuth())
    realdebrid: RealDebridAuth = Field(validation_alias="RealDebrid", default=RealDebridAuth())
    reddit: RedditAuth = Field(validation_alias="Reddit", default=RedditAuth())
    xxxbunker: XXXBunkerAuth = Field(validation_alias="XXXBunker", default=XXXBunkerAuth())
