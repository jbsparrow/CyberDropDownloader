from cyberdrop_dl import __version__ as current_version
from cyberdrop_dl.utils.constants import PRERELEASE_TAGS

FORUMS = {
    "celebforum": "celebforum.to",
    "f95zone": "f95zone.to",
    "leakedmodels": "leakedmodels.com",
    "nudostar": "nudostar.com",
    "xbunker": "xbunker.nu",
    "socialmediagirls": "socialmediagirls.com",
}

WEBSITES = {
    "bunkr": "bunkr",
    "bunkrr": "bunkrr",
    "coomer": "coomer",
    "cyberdrop": "cyberdrop",
    "cyberfile": "cyberfile",
    "e-hentai": "e-hentai",
    "erome": "erome",
    "fapello": "fapello",
    "gofile": "gofile",
    "host.church": "host.church",
    "hotpic": "hotpic",
    "ibb.co": "ibb.co",
    "imageban": "imageban",
    "imagepond.net": "imagepond.net",
    "img.kiwi": "img.kiwi",
    "imgbox": "imgbox",
    "imgur": "imgur",
    "jpeg.pet": "jpeg.pet",
    "jpg.church": "jpg.church",
    "jpg.fish": "jpg.fish",
    "jpg.fishing": "jpg.fishing",
    "jpg.homes": "jpg.homes",
    "jpg.pet": "jpg.pet",
    "jpg1.su": "jpg1.su",
    "jpg2.su": "jpg2.su",
    "jpg3.su": "jpg3.su",
    "jpg4.su": "jpg4.su",
    "jpg5.su": "jpg5.su",
    "kemono": "kemono",
    "mediafire": "mediafire",
    "nudostar.tv": "nudostar.tv",
    "omegascans": "omegascans",
    "pimpandhost": "pimpandhost",
    "pixeldrain": "pixeldrain",
    "postimg": "postimg",
    "realbooru": "realbooru",
    "real-debrid": "real-debrid",
    "redd.it": "redd.it",
    "reddit": "reddit",
    "redgifs": "redgifs",
    "rule34.xxx": "rule34.xxx",
    "rule34.xyz": "rule34.xyz",
    "rule34vault": "rule34vault",
    "saint": "saint",
    "scrolller": "scrolller",
    "toonily": "toonily",
    "tokyomotion.net": "tokyomotion.net",
    "xbunkr": "xbunkr",
    "xxxbunker": "xxxbunker",
}

if next((tag for tag in PRERELEASE_TAGS if tag in current_version), False):
    FORUMS["simpcity"] = "simpcity"

SUPPORTED_SITES = FORUMS | WEBSITES

SUPPORTED_SITES_DOMAINS = list(SUPPORTED_SITES.values())
