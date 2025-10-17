from enum import auto

from cyberdrop_dl.compat import MayBeUpperStrEnum


class Hashing(MayBeUpperStrEnum):
    OFF = auto()
    IN_PLACE = auto()
    POST_DOWNLOAD = auto()
