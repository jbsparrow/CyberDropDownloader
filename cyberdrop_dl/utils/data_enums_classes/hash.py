from enum import Enum


class Hashing(Enum):
    OFF = 0
    IN_PLACE = 1
    POST_DOWNLOAD = 2

    @classmethod
    def _missing_(cls, value):
        try:
            return cls[str(value.upper())]
        except KeyError:
            return cls.OFF

    def __eq__(self, value):
        return self.value == value or self.name == value or super().__eq__(value)
