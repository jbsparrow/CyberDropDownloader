
from enum import StrEnum
class SupportedForums(StrEnum):
    celebforum = "celebforum.to"
    f95zone = "f95zone.to"
    leakedmodels = "leakedmodels.com"
    nudostar = "nudostar.com"
    xbunker = "xbunker.nu"


class SupportedHosts(StrEnum):
    bunkr = "bunkr"
    bunkrr = "bunkrr"
    celebforum = "celebforum"
    coomer = "coomer"
    cyberdrop = "cyberdrop"
    cyberfile = "cyberfile"
    e_hentai = "e-hentai"
    erome = "erome"
    f95zone = "f95zone"
    fapello = "fapello"
    gofile = "gofile"
    host_church = "host.church"
    hotpic = "hotpic"
    ibb_co = "ibb.co"
    imageban = "imageban"
    imagepond_net = "imagepond.net"
    img_kiwi = "img.kiwi"
    imgbox = "imgbox"
    imgur = "imgur"
    jpeg_pet = "jpeg.pet"
    jpg_church = "jpg.church"
    jpg_fish = "jpg.fish"
    jpg_fishing = "jpg.fishing"
    jpg_homes = "jpg.homes"
    jpg_pet = "jpg.pet"
    jpg1_su = "jpg1.su"
    jpg2_su = "jpg2.su"
    jpg3_su = "jpg3.su"
    jpg4_su = "jpg4.su"
    jpg5_su = "jpg5.su"
    kemono = "kemono"
    leakedmodels = "leakedmodels"
    mediafire = "mediafire"
    nudostar_com = "nudostar.com"
    nudostar_tv = "nudostar.tv"
    omegascans = "omegascans"
    pimpandhost = "pimpandhost"
    pixeldrain = "pixeldrain"
    postimg = "postimg"
    realbooru = "realbooru"
    real_debrid = "real-debrid"
    redd_it = "redd.it"
    reddit = "reddit"
    redgifs = "redgifs"
    rule34_xxx = "rule34.xxx"
    rule34_xyz = "rule34.xyz"
    rule34vault = "rule34vault"
    saint = "saint"
    scrolller = "scrolller"
    socialmediagirls = "socialmediagirls"
    toonily = "toonily"
    tokyomotion_net = "tokyomotion.net"
    xbunker = "xbunker"
    xbunkr = "xbunkr"
    xxxbunker = "xxxbunker"

class SupportedHostsDebug(SupportedHosts):
    simpcity="simpcity"

class SupportedSites(SupportedHosts,SupportedForums):
    pass
class SupportedDebugSites(SupportedHostsDebug,SupportedForums):
    pass


