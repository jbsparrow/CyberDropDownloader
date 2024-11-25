from enum import IntEnum


class Hashing(IntEnum):
    OFF = 0
    IN_PLACE = 1
    POST_DOWNLOAD = 2

    @classmethod
    def _missing_(cls, value):
        try:
            return cls[str(value.upper())]
        except KeyError as e:
            raise e
