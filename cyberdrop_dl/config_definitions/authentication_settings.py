from pydantic import BaseModel, Field

from .custom_types import AliasModel


class ForumAuth(BaseModel):
    celebforum_xf_user_cookie: str = ""
    celebforum_username: str = ""
    celebforum_password: str = ""
    f95zone_xf_user_cookie: str = ""
    f95zone_username: str = ""
    f95zone_password: str = ""
    leakedmodels_xf_user_cookie: str = ""
    leakedmodels_username: str = ""
    leakedmodels_password: str = ""
    nudostar_xf_user_cookie: str = ""
    nudostar_username: str = ""
    nudostar_password: str = ""
    simpcity_xf_user_cookie: str = ""
    simpcity_username: str = ""
    simpcity_password: str = ""
    socialmediagirls_xf_user_cookie: str = ""
    socialmediagirls_username: str = ""
    socialmediagirls_password: str = ""
    xbunker_xf_user_cookie: str = ""
    xbunker_username: str = ""
    xbunker_password: str = ""


class CoomerAuth(BaseModel):
    session: str = ""


class XXXBunkerAuth(BaseModel):
    PHPSESSID: str = ""


class ImgurAuth(BaseModel):
    client_id: str = ""


class JDownloaderAuth(AliasModel):
    username: str = Field("", validation_alias="jdownloader_username")
    password: str = Field("", validation_alias="jdownloader_password")
    device: str = Field("", validation_alias="jdownloader_device")


class RedditAuth(BaseModel):
    personal_use_script: str = ""
    secret: str = ""


class GoFileAuth(AliasModel):
    api_key: str = Field("", validation_alias="gofile_api_key")


class PixeldrainAuth(AliasModel):
    api_key: str = Field("", validation_alias="pixeldrain_api_key")


class RealDebridAuth(AliasModel):
    api_key: str = Field("", validation_alias="realdebrid_api_key")


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
