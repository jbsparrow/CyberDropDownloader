from pydantic import BaseModel, SecretStr


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


class JDownloaderAuth(BaseModel):
    username: SecretStr = ""
    password: SecretStr = ""
    device: SecretStr = ""


class ApiKeyAuth(BaseModel):
    api_key: SecretStr = ""


class RedditAuth(BaseModel):
    personal_use_script: SecretStr = ""
    secret: SecretStr = ""


class AuthSettings(BaseModel):
    coomer: CoomerAuth
    forums: ForumAuth
    gofile: ApiKeyAuth
    imgur: ImgurAuth
    jdownloader: JDownloaderAuth
    pixeldrain: ApiKeyAuth
    realdebrid: ApiKeyAuth
    reddit: RedditAuth
    xxxbunker: XXXBunkerAuth
