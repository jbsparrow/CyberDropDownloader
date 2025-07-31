from enum import StrEnum, auto


class Hashing(StrEnum):
    OFF = auto()
    IN_PLACE = auto()
    POST_DOWNLOAD = auto()

    @classmethod
    def _missing_(cls, value: object):
        try:
            return cls[str(value).upper()]
        except KeyError as e:
            raise e
