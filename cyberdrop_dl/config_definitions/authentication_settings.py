from pydantic import BaseModel


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


class GoFileAuth(BaseModel):
    gofile_api_key: str = ""


class ImgurAuth(BaseModel):
    imgur_client_id: str = ""


class JDownloaderAuth(BaseModel):
    jdownloader_username: str = ""
    jdownloader_password: str = ""
    jdownloader_device: str = ""


class PixelDrainAuth(BaseModel):
    pixeldrain_api_key: str = ""


class RealDebridAuth(BaseModel):
    realdebrid_api_key: str = ""


class RedditAuth(BaseModel):
    reddit_personal_use_script: str = ""
    reddit_secret: str = ""


class AuthSettings(BaseModel):
    coomer: CoomerAuth
    forums: ForumAuth
    imgur: ImgurAuth
    xxxbunker: XXXBunkerAuth
    gofile: GoFileAuth
    jdownloader: JDownloaderAuth
    pixeldrain: PixelDrainAuth
    realdebrid: RealDebridAuth
    reddit: RedditAuth
