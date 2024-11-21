from pydantic import BaseModel

from .authentication_settings import AuthSettings
from .config_settings import ConfigSettings
from .global_settings import GlobalSettings


class CDLSettings(BaseModel):
    authentication_settings: AuthSettings
    config_settings: ConfigSettings
    global_settings: GlobalSettings
