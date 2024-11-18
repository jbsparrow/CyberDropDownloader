from enum import Enum 

class Hashing(Enum):
    OFF= 0
    IMPLACE = 1
    POST_DOWNLOAD = 2

class Dedupe(Enum):
    OFF = 0
    KEEP_OLDEST = 1
    KEEP_NEWEST = 2
    KEEP_OLDEST_ALL = 3
    KEEP_NEWEST_ALL = 4
 


