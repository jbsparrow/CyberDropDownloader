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


class Dedupe(Enum):
    OFF = 0
    KEEP_OLDEST = 1
    KEEP_NEWEST = 2
    KEEP_OLDEST_ALL = 3
    KEEP_NEWEST_ALL = 4

    @classmethod
    def _missing_(cls, value):
        try:
            return cls[str(value.upper())]
        except KeyError:
            return cls.OFF

    def compare(self, value):
        return self.value == value or self.name == value

    def __eq__(self, value):
        return self.value == value or self.name == value or super().__eq__(value)
