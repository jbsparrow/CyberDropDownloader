---
description: These are the websites supported by `cyberdrop-dl`
icon: globe-pointer
---

<!-- markdownlint-disable MD033 MD034 MD041 -->

# Supported Websites

For a full list of all supported sites, see [supported sites](#supported-sites)

## Password Protected Content Hosts

`cyberdrop-dl` can download password protected files and folders from these hosts. User must include the password as a query parameter in the input URL, adding `?password=<URL_PASSWORD>` to it.

Example: `https://gofile.io/d/xUGg-sghx?password=1234`

| Domain                         |
| ------------------------------ |
| Chevereto sites (`ImgLike`)    |
| Cyberfile                      |
| Filester                       |
| GoFile                         |
| Iceyfile.com                   |
| Imagepond.net                  |
| Koofr.eu                       |
| Transfer.it                    |
| Sites supported by Real-Debrid |

## Additional supported sites with Real-Debrid

`cyberdrop-dl` has integration with Real-Debrid as download service to support additional hosts. In order to enable Real-Debrid, user must provide their API token
inside their config file. You can get your API token from this URL (you must be logged into Real-Debrid to view it): <https://real-debrid.com/apitoken>

Supported domains via Real-Debrid include `rapidgator`, `4shared.com`, `fikper.com`, `k2s`, `etc`.
List of all supported domains can be found here (250+): <https://api.real-debrid.com/rest/1.0/hosts/domains>

{% hint style="info" %}
Real-Debrid will only be used for _unsupported_ sites. To use it for a site that CDL supports, ex: `mega.nz`, you have to disable the `mega.nz` crawler.
See: <https://script-ware.gitbook.io/cyberdrop-dl/reference/config/crawlers#disabled>
{% endhint %}

## Additional supported sites with JDownloader

`cyberdrop-dl` has integration with JDownloader as a backup downloader for unsupported sites hosts. `cyberdrop-dl` will send unsupported URLs to a running instance of JDownloader
with a custom setup to make sure JDownloader put files on the same folder and with the same name `cyberdrop-dl` would have used.

You must provide your MyJDownloader credentials in your config file to connect to JDownloader

{% hint style="info" %}
JDownloader will only be used for _unsupported_ sites. To use it for a site that CDL supports, ex: `mega.nz`, you have to disable the `mega.nz` crawler.
See: <https://script-ware.gitbook.io/cyberdrop-dl/reference/config/crawlers#disabled>
{% endhint %}

<!-- START_SUPPORTED_SITES -->

## Supported sites

List of sites supported by cyberdrop-dl-patched as of version 10.8.0

### 1fichier

**Primary URL**: [https://1fichier.com](https://1fichier.com)

**Supported Domains**: `1fichier.com`, `alterupload.com`, `cjoint.net`, `desfichiers.com`, `dfichiers.com`, `dl4free.com`, `megadl.fr`, `mesfichiers.org`, `piecejointe.net`, `pjointe.com`, `tenvoi.com`

**Supported Paths**:

- File:
  - `?<file_id>`

### 4chan

**Primary URL**: [https://boards.4chan.org](https://boards.4chan.org)

**Supported Domains**: `4chan.*`

**Supported Paths**:

- Board:
  - `/<board>`
- Thread:
  - `/<board>/thread/<thread_id>`

### 8Muses

**Primary URL**: [https://comics.8muses.com](https://comics.8muses.com)

**Supported Domains**: `8muses.*`

**Supported Paths**:

- Album:
  - `/comics/album/...`

### ABStream

**Primary URL**: [https://abstream.to](https://abstream.to)

**Supported Domains**: `abstream.*`

**Supported Paths**:

- File:
  - `/d/<file_id>`
  - `/e/<file_id>`
  - `/embed-<file_id>.html`
  - `/embed/<file_id>`
  - `/file/<file_id>`

### Acast.com

**Primary URL**: [https://www.acast.com](https://www.acast.com)

**Supported Domains**: `acast.com`

**Supported Paths**:

- Episode:
  - `/<show_id>/episodes/<episode_id>`
- Show:
  - `/<show_id>`

### Adobe Lightroom

**Primary URL**: [https://lightroom.adobe.com](https://lightroom.adobe.com)

**Supported Domains**: `lightroom.adobe`

**Supported Paths**:

- Shared Album:
  - `/shares/<space_id>`

### AllPornComix

**Primary URL**: [https://forum.allporncomix.com](https://forum.allporncomix.com)

**Supported Domains**: `allporncomix.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### Anontransfer.com

**Primary URL**: [https://anontransfer.com](https://anontransfer.com)

**Supported Domains**: `anontransfer.com`

**Supported Paths**:

- Direct Link:
  - `/download-direct.php?dir=<file_id>&file=<filename>`
  - `/uploads/<file_id>/<filename>`
- File:
  - `/d/<file_id>`
- Folder:
  - `/f/<folder_uuid>`

### AnySex

**Primary URL**: [https://anysex.com](https://anysex.com)

**Supported Domains**: `anysex.com`

**Supported Paths**:

- Album:
  - `/photos/<album_id>/...`
- Photo Search:
  - `/photos/search/...`
- Search:
  - `/search/...`
- Video:
  - `/video/<video_id>/...`

### APK Mirror

**Primary URL**: [https://www.apkmirror.com](https://www.apkmirror.com)

**Supported Domains**: `apkmirror.com`

**Supported Paths**:

- APK:
  - `/apk/<developer>/<application>/<release>/<variant>-download`

### Archive.org

**Primary URL**: [https://archive.org](https://archive.org)

**Supported Domains**: `archive.org`

**Supported Paths**:

- Files:
  - `/details/<identifier>/<subpath>`
  - `/download/<identifier>/<subpath>`
- Item:
  - `/details/<identifier>`
  - `/download/<identifier>`

### ArchiveBate

**Primary URL**: [https://www.archivebate.store](https://www.archivebate.store)

**Supported Domains**: `archivebate.*`

**Supported Paths**:

- Video:
  - `/watch/<video_id>`

### aShemaleTube

**Primary URL**: [https://www.ashemaletube.com](https://www.ashemaletube.com)

**Supported Domains**: `ashemaletube.*`

**Supported Paths**:

- Model:
  - `/creators/...`
  - `/model/...`
  - `/pornstars/...`
- Playlist:
  - `/playlists/...`
- User:
  - `/profiles/...`
- Video:
  - `/videos/...`

### Bandcamp

**Primary URL**: [https://bandcamp.com](https://bandcamp.com)

**Supported Domains**: `bandcamp.*`

**Supported Paths**:

- Album:
  - `/album/<slug>`
- Song:
  - `/track/<slug>`

### Beeg.com

**Primary URL**: [https://beeg.com](https://beeg.com)

**Supported Domains**: `beeg.com`

**Supported Paths**:

- Video:
  - `/<video_id>`
  - `/video/<video_id>`

### Bellazon

**Primary URL**: [https://www.bellazon.com/main](https://www.bellazon.com/main)

**Supported Domains**: `bellazon.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Invision

### BestPrettyGirl

**Primary URL**: [https://bestprettygirl.com](https://bestprettygirl.com)

**Supported Domains**: `bestprettygirl.com`

**Supported Paths**:

- All Posts:
  - `/posts/`
- Category:
  - `/category/<category_slug>`
- Post:
  - `/<post_slug>/`
- Tag:
  - `/tag/<tag_slug>`

### Box

**Primary URL**: [https://www.box.com](https://www.box.com)

**Supported Domains**: `.box.com`

**Supported Paths**:

- Shared file/folder:
  - `/embed/s?sh=<share_name>`
  - `/embed_widget/s?sh=<share_name>`
  - `/s/<share_name>`
  - `/s/<share_name>/file/<file_id>`
  - `/s/<share_name>/folder/<folder_id>`
  - `/s?sh=<share_name>`

### Bunkr

**Primary URL**: [https://bunkr.cr](https://bunkr.cr)

**Supported Domains**: `bunkr.*`, `bunkr.black`, `bunkr.cr`, `bunkr.is`, `bunkr.la`, `bunkr.se`, `bunkr.su`, `bunkrr.su`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- File:
  - `/d/<slug>`
  - `/f/<slug>`
  - `/i/<slug>`
- Stream redirect:
  - `/<slug>`
- Video:
  - `/v/<slug>`

### Bunkr-Albums

**Primary URL**: [https://balbums.st](https://balbums.st)

**Supported Domains**: `balbums.st`, `bunkr-albums.io`

**Supported Paths**:

- Search:
  - `/?search=<query>`

### BuzzHeavier

**Primary URL**: [https://buzzheavier.com](https://buzzheavier.com)

**Supported Domains**: `buzzheavier.com`

**Supported Paths**:

- Direct Links:

### Camwhores.tv

**Primary URL**: [https://www.camwhores.tv](https://www.camwhores.tv)

**Supported Domains**: `camwhores.tv`

**Supported Paths**:

- Category:
  - `/categories/<name>/`
- Search:
  - `/search/<query>/`
- Tag:
  - `/tags/<name>/`
- Video:
  - `/videos/<id>/<slug>`

### Cara.app

**Primary URL**: [https://cara.app](https://cara.app)

**Supported Domains**: `cara.app`

**Supported Paths**:

- Post:
  - `/post/<id>`
- User:
  - `/<username>`

### Catbox

**Primary URL**: [https://catbox.moe](https://catbox.moe)

**Supported Domains**: `files.catbox.moe`, `files.fatbox.moe`, `litter.catbox.moe`, `litter.fatbox.moe`

**Supported Paths**:

- Direct Links:

### CelebForum

**Primary URL**: [https://celebforum.cc](https://celebforum.cc)

**Supported Domains**: `celeb.su`, `celebforum.cc`, `celebforum.to`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### Chevereto

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Album:
  - `/a/<id>`
  - `/a/<name>.<id>`
  - `/album/<id>`
  - `/album/<name>.<id>`
- Category:
  - `/category/<name>`
- Direct Links:
- Image:
  - `/image/<id>`
  - `/image/<name>.<id>`
  - `/img/<id>`
  - `/img/<name>.<id>`
- Profile:
  - `/<user_name>`
- Video:
  - `/video/<id>`
  - `/video/<name>.<id>`
  - `/videos/<id>`
  - `/videos/<name>.<id>`

### Clonr

**Primary URL**: [https://clonr.co](https://clonr.co)

**Supported Domains**: `clonr.*`

**Supported Paths**:

- Clone:
  - `/<clone_id>`

### cloud.mail.ru

**Primary URL**: [https://cloud.mail.ru](https://cloud.mail.ru)

**Supported Domains**: `cloud.mail.ru`

**Supported Paths**:

- Public files / folders:
  - `/public/<web_path>`

### CloudflareStream

**Primary URL**: [https://cloudflarestream.com](https://cloudflarestream.com)

**Supported Domains**: `cloudflarestream.com`, `videodelivery.net`

**Supported Paths**:

- Public Video:
  - `/<video_uid>`
  - `/<video_uid>/iframe`
  - `/<video_uid>/watch`
  - `/embed/___.js?video=<video_uid>`
- Restricted Access Video:
  - `/<jwt_access_token>`
  - `/<jwt_access_token>/iframe`
  - `/<jwt_access_token>/watch`
  - `/embed/___.js?video=<jwt_access_token>`

### Clyp.it

**Primary URL**: [https://clyp.it](https://clyp.it)

**Supported Domains**: `clyp.it`

**Supported Paths**:

- Audio:
  - `/<audio_id>`
- User:
  - `/user/<user_id>`

### CrazyShit

**Primary URL**: [https://crazyshit.com](https://crazyshit.com)

**Supported Domains**: `crazyshit.*`

**Supported Paths**:

- Series:
  - `/series/<name>`
- Video:
  - `/cnt/medias/<slug>`

### Cyberdrop

**Primary URL**: [https://cyberdrop.cr](https://cyberdrop.cr)

**Supported Domains**: `cyberdrop.*`, `cyberdrop.cr`, `cyberdrop.me`, `cyberdrop.to`, `k1-cd.cdn.gigachad-cdn.ru`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Direct links:
  - `/api/file/d/<file_id>`
- File:
  - `/e/<file_id>`
  - `/f/<file_id>`

### Cyberfile

**Primary URL**: [https://cyberfile.me](https://cyberfile.me)

**Supported Domains**: `cyberfile.*`

**Supported Paths**:

- Files:
  - `/<file_id>`
  - `/<file_id>/<file_name>`
- Public Folders:
  - `/folder/<folder_id>`
  - `/folder/<folder_id>/<folder_name>`
- Shared folders:
  - `/shared/<share_key>`

### Daftporn

**Primary URL**: [https://www.daftporn.com](https://www.daftporn.com)

**Supported Domains**: `daftporn.*`

**Supported Paths**:

- Video:
  - `/extreme-videos/<slug>`

### Dailymotion

**Primary URL**: [https://www.dailymotion.com](https://www.dailymotion.com)

**Supported Domains**: `dailymotion.*`

**Supported Paths**:

- Playlist:
  - `/playlist/<slug>`
- Video:
  - `/video/<video_uid>`

### DesiVideo

**Primary URL**: [https://desivideo.net](https://desivideo.net)

**Supported Domains**: `desivideo.net`

**Supported Paths**:

- Search:
  - `/search?s=<query>`
- Video:
  - `/videos/<video_id>/...`

### DirectHttpFile

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

### DirtyShip

**Primary URL**: [https://dirtyship.com](https://dirtyship.com)

**Supported Domains**: `dirtyship.*`

**Supported Paths**:

- Category:
  - `/category/<name>`
- Tag:
  - `/tag/<name>`
- Video:
  - `/<slug>`

### Discourse

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Attachments:
  - `/uploads/...`
- Topic:
  - `/t/<topic_name>/<topic_id>`
  - `/t/<topic_name>/<topic_id>/<post_number>`

**Notes**

- If the URL includes <post_number>, posts with a number lower that it won't be scraped

### DoodStream

**Primary URL**: [https://doodstream.com](https://doodstream.com)

**Supported Domains**: `all3do.com`, `d000d.com`, `do7go.com`, `dood.re`, `dood.yt`, `doodcdn.*`, `doodstream.*`, `doodstream.co`, `dooodster.com`, `myvidplay.com`, `playmogo.com`, `vidply.com`

**Supported Paths**:

- Video:
  - `/e/<video_id>`

### Dropbox

**Primary URL**: [https://www.dropbox.com](https://www.dropbox.com)

**Supported Domains**: `dropbox.*`

**Supported Paths**:

- File:
  - `/s/...`
  - `/scl/fi/<link_key>?rlkey=...`
  - `/scl/fo/<link_key>/<secure_hash>?preview=<filename>&rlkey=...`
- Folder:
  - `/scl/fo/<link_key>/<secure_hash>?rlkey=...`
  - `/sh/...`

### E-Hentai

**Primary URL**: [https://e-hentai.org](https://e-hentai.org)

**Supported Domains**: `e-hentai.*`

**Supported Paths**:

- Album:
  - `/g/...`
- File:
  - `/s/...`

### E621

**Primary URL**: [https://e621.net](https://e621.net)

**Supported Domains**: `e621.net`

**Supported Paths**:

- Pools:
  - `/pools/<pool_id>`
- Post:
  - `/posts/<post_id>`
- Tags:
  - `/posts?tags=<tags>`

### eFukt

**Primary URL**: [https://efukt.com](https://efukt.com)

**Supported Domains**: `efukt.com`

**Supported Paths**:

- Gif:
  - `/view.gif.php?id=<id>`
- Homepage:
  - `/`
- Photo:
  - `/pics/....`
- Series:
  - `/series/<series_name>`
- Video:
  - `/...`

### ePorner

**Primary URL**: [https://www.eporner.com](https://www.eporner.com)

**Supported Domains**: `eporner.*`

**Supported Paths**:

- Categories:
  - `/cat/...`
- Channels:
  - `/channel/...`
- Gallery:
  - `/gallery/...`
- Photo:
  - `/photo/...`
- Pornstar:
  - `/pornstar/...`
- Profile:
  - `/profile/...`
- Search:
  - `/search/...`
- Search Photos:
  - `/search-photos/...`
- Video:
  - `/<video_name>-<video-id>`
  - `/embed/<video_id>`
  - `/hd-porn/<video_id>`

### Erome

**Primary URL**: [https://www.erome.com](https://www.erome.com)

**Supported Domains**: `erome.*`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Profile:
  - `/<name>`
- Search:
  - `/search?q=<query>`

### Erome.fan

**Primary URL**: [https://erome.fan](https://erome.fan)

**Supported Domains**: `erome.fan`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Profile:
  - `/a/category/<name>`
- Search:
  - `/search/<query>`

### EveriaClub

**Primary URL**: [https://everia.club](https://everia.club)

**Supported Domains**: `everia.club`

**Supported Paths**:

- All Posts:
  - `/posts/`
- Category:
  - `/category/<category_slug>`
- Post:
  - `/<post_slug>/`
- Tag:
  - `/tag/<tag_slug>`

### F95Zone

**Primary URL**: [https://f95zone.to](https://f95zone.to)

**Supported Domains**: `f95zone.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### Fapello.com

**Primary URL**: [https://fapello.com](https://fapello.com)

**Supported Domains**: `fapello.com`

**Supported Paths**:

- Individual Post:
  - `/<model_nam>/<post_id>`
- Model:
  - `/<name>`

### Fileditch

**Primary URL**: [https://fileditchfiles.me](https://fileditchfiles.me)

**Supported Domains**: `fileditch.*`, `theditch.st`

**Supported Paths**:

- File:
  - `/alpha7/<file_id>/<name>`
  - `/beta123/<file_id>/<name>`
  - `/file.php?f=<file_id>`
  - `/temp/<file_id>/<name>`
- Short URL:
  - `https://theditch.st/<short_id>`

### Filester

**Primary URL**: [https://filester.me](https://filester.me)

**Supported Domains**: `filester.*`

**Supported Paths**:

- File:
  - `/d/<slug>`
- Folder:
  - `/f/<slug>`

### Flickr

**Primary URL**: [https://www.flickr.com](https://www.flickr.com)

**Supported Domains**: `flickr.*`

**Supported Paths**:

- Album:
  - `/photos/<user_nsid>/albums/<photoset_id>/...`
- Photo:
  - `/photos/<user_nsid>/<photo_id>/...`

### Forums.plex.tv

**Primary URL**: [https://forums.plex.tv](https://forums.plex.tv)

**Supported Domains**: `forums.plex.tv`

**Supported Paths**:

- Attachments:
  - `/uploads/...`
- Topic:
  - `/t/<topic_name>/<topic_id>`
  - `/t/<topic_name>/<topic_id>/<post_number>`

**Notes**

- If the URL includes <post_number>, posts with a number lower that it won't be scraped

### FSIBlog

**Primary URL**: [https://fsiblog5.com](https://fsiblog5.com)

**Supported Domains**: `fsiblog.club`, `fsiblog.com`, `fsiblog1.club`, `fsiblog1.com`, `fsiblog2.club`, `fsiblog2.com`, `fsiblog3.club`, `fsiblog3.com`, `fsiblog4.club`, `fsiblog4.com`, `fsiblog5.club`, `fsiblog5.com`

**Supported Paths**:

- Posts:
  - `/<category>/<title>`
- Search:
  - `?s=<query>`

### FuckingFast

**Primary URL**: [https://fuckingfast.co](https://fuckingfast.co)

**Supported Domains**: `fuckingfast.co`

**Supported Paths**:

- Direct links:
  - `/<file_id>`

### FuXXX

**Primary URL**: [https://fuxxx.com](https://fuxxx.com)

**Supported Domains**: `fuxxx.com`, `fuxxx.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Fyptt

**Primary URL**: [https://fyptt.to](https://fyptt.to)

**Supported Domains**: `fyptt.*`

**Supported Paths**:

- Post:
  - `/<post_id>/...`

### GenericKVS

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Video:
  - `/video/<slug>`
  - `/videos/<slug>`

### GenericVideo

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Video:
  - `/...`

### GifHQ

**Primary URL**: [https://gifhq.com](https://gifhq.com)

**Supported Domains**: `gifhq.*`

**Supported Paths**:

- Post:
  - `/post/<post_id>`
- Subreddit:
  - `/r/<subreddit>`
  - `/r/<subreddit>/best/<period>`
  - `/r/<subreddit>/best/<period>?content=images`
  - `/r/<subreddit>/best/<period>?content=videos`

### Giphy

**Primary URL**: [https://giphy.com](https://giphy.com)

**Supported Domains**: `giphy.*`

**Supported Paths**:

- Direct Link:
  - `https://media*.giphy.com/media/<gif_id>`
- Gif:
  - `/gifs/<slug>-<gif-id>`

### GirlsReleased

**Primary URL**: [https://www.girlsreleased.com](https://www.girlsreleased.com)

**Supported Domains**: `girlsreleased.*`

**Supported Paths**:

- Model:
  - `/model/<model_id>/<model_name>`
- Set:
  - `/set/<set_id>`
- Site:
  - `/site/<site>`

### GoFile

**Primary URL**: [https://gofile.io](https://gofile.io)

**Supported Domains**: `gofile.*`

**Supported Paths**:

- Direct link:
  - `/download/<content_id>/<filename>`
  - `/download/web/<content_id>/<filename>`
- Folder / File:
  - `/d/<content_id>`

**Notes**

- Use `password` as a query param to download password protected folders
- ex: https://gofile.io/d/ABC654?password=1234

### GoogleDrive

**Primary URL**: [https://drive.google.com](https://drive.google.com)

**Supported Domains**: `docs.google`, `drive.google`, `drive.usercontent.google.com`

**Supported Paths**:

- Docs:
  - `/document/d/<file_id>`
- Files:
  - `/download?id=<file_id>`
  - `/file/d/<file_id>`
- Folders:
  - `/drive/folders/<folder_id>`
  - `/embeddedfolderview/<folder_id>`
  - `/embeddedfolderview?id=<folder_id>`
- Sheets:
  - `/spreadsheets/d/<file_id>`
- Slides:
  - `/presentation/d/<file_id>`

**Notes**

- You can download sheets, slides and docs in a custom format by using it as a query param.
  ex: https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=ods
  Valid Formats:

document:

- docx (default)
- epub
- md
- odt
- pdf
- rtf
- txt
- zip

presentation:

- odp
- pptx (default)

spreadsheets:

- csv
- html
- ods
- tsv
- xslx (default)

### GooglePhotos

**Primary URL**: [https://photos.google.com](https://photos.google.com)

**Supported Domains**: `photos.app.goo.gl`, `photos.google.com`

**Supported Paths**:

- Album:
  - `/share/<album_id>`
- Photo:
  - `/album/<album_id>/photo/<photo_id>`

**Notes**

- Only downloads 'optimized' images, NOT original quality
- Can NOT download videos

### GoonBox

**Primary URL**: [https://goonbox.cr](https://goonbox.cr)

**Supported Domains**: `cuckcapital.cr`, `goonbox.*`, `goonbox.cr`, `host.church`, `jpeg.pet`, `jpg.church`, `jpg.fish`, `jpg.fishing`, `jpg.homes`, `jpg.pet`, `jpg1.su`, `jpg2.su`, `jpg3.su`, `jpg4.su`, `jpg5.su`, `jpg6.su`, `jpg7.cr`, `selti-delivery.ru`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Direct Links:
- Image:
  - `/img/<image_id>`
- User:
  - `/u/<username>`

### GUpload

**Primary URL**: [https://gupload.xyz](https://gupload.xyz)

**Supported Domains**: `gupload.*`

**Supported Paths**:

- Video:
  - `/data/e/<video_id>`

### HClips

**Primary URL**: [https://hclips.com](https://hclips.com)

**Supported Domains**: `hclips.com`, `hclips.tube`, `privatehomeclips.com`, `privatehomeclips.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### HDZog

**Primary URL**: [https://hdzog.com](https://hdzog.com)

**Supported Domains**: `hdzog.com`, `hdzog.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Hitomi.la

**Primary URL**: [https://hitomi.la](https://hitomi.la)

**Supported Domains**: `hitomi.la`

**Supported Paths**:

- Collection:
  - `/artist/<slug>`
  - `/character/<slug>`
  - `/group/<slug>`
  - `/series/<slug>`
  - `/tag/<slug>`
  - `/type/<slug>`
- Gallery:
  - `/anime/<name>-<gallery_id>.html`
  - `/cg/<name>-<gallery_id>.html`
  - `/doujinshi/<name>-<gallery_id>.html`
  - `/galleries/<name>-<gallery_id>.html`
  - `/gamecg/<name>-<gallery_id>.html`
  - `/imageset/<name>-<gallery_id>.html`
  - `/manga/<name>-<gallery_id>.html`
  - `/reader/<name>-<gallery_id>.html`
- Index:
  - `/index-<language>.html`
- Search:
  - `/search.html?<query>`

### Hohoj

**Primary URL**: [https://hohoj.tv](https://hohoj.tv)

**Supported Domains**: `hohoj.*`

**Supported Paths**:

- Video:
  - `/video?id=<video_id>`

### HotLeaksTV

**Primary URL**: [https://hotleaks.tv](https://hotleaks.tv)

**Supported Domains**: `hotleaks.tv`

**Supported Paths**:

- Model:
  - `/<model_id>`
- Video:
  - `/<model_id>/video/<video_id>`

### HotLeakVip

**Primary URL**: [https://hotleak.vip](https://hotleak.vip)

**Supported Domains**: `hotleak.vip`

**Supported Paths**:

- Model:
  - `/<model_id>`
- Video:
  - `/<model_id>/video/<video_id>`

### HotMovs

**Primary URL**: [https://hotmovs.com](https://hotmovs.com)

**Supported Domains**: `hotmovs.com`, `hotmovs.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### HotPic

**Primary URL**: [https://hotpic.cc](https://hotpic.cc)

**Supported Domains**: `2385290.xyz`, `hotpic.*`, `myhostdata.space`

**Supported Paths**:

- Album:
  - `/album/...`
- Image:
  - `/i/...`

### Iceyfile

**Primary URL**: [https://iceyfile.com](https://iceyfile.com)

**Supported Domains**: `iceyfile.*`

**Supported Paths**:

- Files:
  - `/<file_id>`
  - `/<file_id>/<file_name>`
- Public Folders:
  - `/folder/<folder_id>`
  - `/folder/<folder_id>/<folder_name>`
- Shared folders:
  - `/shared/<share_key>`

### ImageBam

**Primary URL**: [https://www.imagebam.com](https://www.imagebam.com)

**Supported Domains**: `imagebam.*`

**Supported Paths**:

- Gallery:
  - `/gallery/<id>`
- Gallery or Image:
  - `/view/<id>`
- Image:
  - `/image/<id>`
  - `images<x>.imagebam.com/<id>`
- Thumbnails:
  - `thumbs<x>.imagebam.com/<id>`

### ImagePond

**Primary URL**: [https://www.imagepond.net](https://www.imagepond.net)

**Supported Domains**: `imagepond.net`

**Supported Paths**:

- Album:
  - `/a/<slug>`
- Direct links:
  - `/media/<slug>`
- Image / Video / Archive:
  - `/i/<slug>`
  - `/image/<slug>`
  - `/img/<slug>`
  - `/video/<slug>`
  - `/videos/<slug>`
- User:
  - `/<user_name>`
  - `/user/<user_name>`

### ImageVenue

**Primary URL**: [https://www.imagevenue.com](https://www.imagevenue.com)

**Supported Domains**: `imagevenue.*`

**Supported Paths**:

- Image:
  - `/<image_id>`
  - `/img.php?image=<image_id>`
  - `/view/o?i=<image_id>`
- Thumbnail:
  - `cdn-thumbs.imagevenue.com/.../<image_id>_t.jpg`

### ImgBB

**Primary URL**: [https://ibb.co](https://ibb.co)

**Supported Domains**: `ibb.co`, `imgbb.co`

**Supported Paths**:

- Album:
  - `/album/<album_id>`
- Image:
  - `/<image_id>`
- Profile:
  - `<user_name>.imgbb.co/`

### ImgBox

**Primary URL**: [https://imgbox.com](https://imgbox.com)

**Supported Domains**: `imgbox.*`

**Supported Paths**:

- Album:
  - `/g/...`
- Direct Links:
- Image:
  - `/...`

### ImgLike

**Primary URL**: [https://imglike.com](https://imglike.com)

**Supported Domains**: `imglike.com`

**Supported Paths**:

- Album:
  - `/a/<id>`
  - `/a/<name>.<id>`
  - `/album/<id>`
  - `/album/<name>.<id>`
- Category:
  - `/category/<name>`
- Direct Links:
- Image:
  - `/image/<id>`
  - `/image/<name>.<id>`
  - `/img/<id>`
  - `/img/<name>.<id>`
- Profile:
  - `/<user_name>`
- Video:
  - `/video/<id>`
  - `/video/<name>.<id>`
  - `/videos/<id>`
  - `/videos/<name>.<id>`

### Imgur

**Primary URL**: [https://imgur.com](https://imgur.com)

**Supported Domains**: `imgur.*`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Direct links:
  - `https://i.imgur.com/<image_id>.<ext>`
- Gallery:
  - `/gallery/<slug>-<album_id>`
- Image:
  - `/<image_id>`
  - `/download/<image_id>`

### Imx.to

**Primary URL**: [https://imx.to](https://imx.to)

**Supported Domains**: `imx.to`

**Supported Paths**:

- Gallery:
  - `/g/<gallery_id>`
- Image:
  - `/i/...`
  - `/u/i/...`
- Thumbnail:
  - `/t/...`
  - `/u/t/`

### InPorn

**Primary URL**: [https://inporn.com](https://inporn.com)

**Supported Domains**: `inporn.com`, `inporn.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Koofr

**Primary URL**: [https://koofr.eu](https://koofr.eu)

**Supported Domains**: `k00.fr`, `koofr.eu`, `koofr.net`

**Supported Paths**:

- Public Share:
  - `/links/<content_id>`
  - `https://k00.fr/<short_id>`

### LeakedModels

**Primary URL**: [https://leakedmodels.com/forum](https://leakedmodels.com/forum)

**Supported Domains**: `leakedmodels.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### LeakedZone

**Primary URL**: [https://leakedzone.com](https://leakedzone.com)

**Supported Domains**: `leakedzone.*`

**Supported Paths**:

- Model:
  - `/<model_id>`
- Video:
  - `/<model_id>/video/<video_id>`

### LiveCamRips

**Primary URL**: [https://livecamrips.to](https://livecamrips.to)

**Supported Domains**: `livecamrips.*`

**Supported Paths**:

- Model:
  - `/model/<model_id>`
- Video:
  - `/video/<video_id>`

### Livestreamfails.com

**Primary URL**: [https://livestreamfails.com](https://livestreamfails.com)

**Supported Domains**: `livestreamfails.com`

**Supported Paths**:

- Clip:
  - `/clip/<video_id>`
- Streamer:
  - `/streamer/<streamer_id>`

### Livid.com

**Primary URL**: [https://livid.com](https://livid.com)

**Supported Domains**: `livid.com`

**Supported Paths**:

- Video:
  - `/embed/<video_id>`
  - `/watch/<video_id>`

### Luscious

**Primary URL**: [https://members.luscious.net](https://members.luscious.net)

**Supported Domains**: `luscious.*`

**Supported Paths**:

- Album:
  - `/albums/<name>_<album_id>`
  - `/albums/<name>_<album_id>?only_animated=true`
- Search:
  - `/albums/list?tagged=<query>`

### LuxureTV

**Primary URL**: [https://luxuretv.com](https://luxuretv.com)

**Supported Domains**: `luxuretv.*`

**Supported Paths**:

- Search:
  - `/searchgate/videos/<search>/...`
- Video:
  - `/videos/<name>-<id>.html`

### Masahub

**Primary URL**: [https://masahub.com](https://masahub.com)

**Supported Domains**: `lol49.com`, `masa49.com`, `masafun.net`, `masahub.com`, `masahub2.com`, `vido99.com`

**Supported Paths**:

- Search:
  - `?s=<query>`
- Videos:
  - `/title`

### Mediafire

**Primary URL**: [https://www.mediafire.com](https://www.mediafire.com)

**Supported Domains**: `mediafire.*`

**Supported Paths**:

- File:
  - `/file/<quick_key>`
  - `?<quick_key>`
- Folder:
  - `/folder/<folder_key>`

### Megacloud

**Primary URL**: [https://megacloud.blog](https://megacloud.blog)

**Supported Domains**: `megacloud.*`

**Supported Paths**:

- Embed v3:
  - `/embed-2/v3`

### MegaNz

**Primary URL**: [https://mega.nz](https://mega.nz)

**Supported Domains**: `mega.co.nz`, `mega.io`, `mega.nz`

**Supported Paths**:

- File:
  - `/!#<file_id>!<share_key>`
  - `/file/<file_id>#<share_key>`
  - `/folder/<folder_id>#<share_key>/file/<file_id>`
- Folder:
  - `/F!#<folder_id>!<share_key>`
  - `/folder/<folder_id>#<share_key>`
- Subfolder:
  - `/folder/<folder_id>#<share_key>/folder/<subfolder_id>`

**Notes**

- Downloads can not be resumed. Partial downloads will always be deleted and new downloads will start over

### MissAV

**Primary URL**: [https://missav.ws](https://missav.ws)

**Supported Domains**: `missav.ws`, `njavtv.com`

**Supported Paths**:

- Genres:
  - `/genres/<genre>`
- Labels:
  - `/labels/<label>`
- Makers:
  - `/makers/<maker>`
- Search:
  - `/search/<search>`
- Tags:
  - `/tags/<tag>`
- Video:
  - `/...`

### Mitaku.net

**Primary URL**: [https://mitaku.net](https://mitaku.net)

**Supported Domains**: `mitaku.net`

**Supported Paths**:

- All Posts:
  - `/posts/`
- Category:
  - `/category/<category_slug>`
- Post:
  - `/<post_slug>/`
- Tag:
  - `/tag/<tag_slug>`

### MixDrop

**Primary URL**: [https://mixdrop.sb](https://mixdrop.sb)

**Supported Domains**: `m1xdrop.*`, `mixdrop.*`, `mxdrop.*`

**Supported Paths**:

- File:
  - `/e/<file_id>`
  - `/f/<file_id>`

### Monstercat

**Primary URL**: [https://www.monstercat.com](https://www.monstercat.com)

**Supported Domains**: `monstercat.*`

**Supported Paths**:

- Release:
  - `/release/<slug>`

### Motherless

**Primary URL**: [https://motherless.xxx](https://motherless.xxx)

**Supported Domains**: `motherless.com`, `motherless.xxx`

**Supported Paths**:

- Gallery:
  - `/G<gallery_id>`
  - `/GI<gallery_id>`
  - `/GV<gallery_id>`
- Group:
  - `/g/<group_name>`
  - `/gi/<group_name>`
  - `/gv/<group_name>`
- Image or Video:
  - `/<media_id>`
  - `/G<gallery_id>/<media_id>`
  - `/g/<group_name>/<media_id>`
- User:
  - `/m/<user_name>`
  - `/member/<user_name>`
  - `/u/<user_name>`
  - `/u/<user_name>?t=i`
  - `/u/<user_name>?t=v`
- User galleries:
  - `/galleries/member/<user_name>/...`

### Multporn.net

**Primary URL**: [https://multporn.net](https://multporn.net)

**Supported Domains**: `multporn.net`

**Supported Paths**:

- comic:
  - `/comics/<slug>`
  - `/gay_porn_comics/<slug>`
  - `/hentai_manga/<slug>`
  - `/humor/<slug>`
- video:
  - `/video/<slug>`

### MyDesi

**Primary URL**: [https://lolpol.com](https://lolpol.com)

**Supported Domains**: `fry99.com`, `lolpol.com`, `mydesi.net`

**Supported Paths**:

- Search:
  - `/search/<query>`
- Videos:
  - `/title`

### Naughtymachinima

**Primary URL**: [https://www.naughtymachinima.com](https://www.naughtymachinima.com)

**Supported Domains**: `naughtymachinima.*`

**Supported Paths**:

- Album:
  - `/album/<album_id>`
- Video:
  - `/video/<video_id>`

### nHentai

**Primary URL**: [https://nhentai.net](https://nhentai.net)

**Supported Domains**: `nhentai.net`

**Supported Paths**:

- Collections:
  - `artist`
  - `character`
  - `favorites`
  - `group`
  - `parody`
  - `search`
  - `tag`
- Gallery:
  - `/g/<gallery_id>`

### NoodleMagazine

**Primary URL**: [https://noodlemagazine.com](https://noodlemagazine.com)

**Supported Domains**: `noodlemagazine.*`

**Supported Paths**:

- Search:
  - `/video/<search_query>`
- Video:
  - `/watch/<video_id>`

### Nova

**Primary URL**: [https://nova.storage](https://nova.storage)

**Supported Domains**: `nova.storage`

**Supported Paths**:

- Filesystem:
  - `/api/filesystem/<path>...`
  - `/d/<id>`

**Notes**

- text files will not be downloaded but their content will be parsed for URLs

### nsfw.xxx

**Primary URL**: [https://nsfw.xxx](https://nsfw.xxx)

**Supported Domains**: `nsfw.xxx`

**Supported Paths**:

- Category:
  - `/category/<name>`
- Post:
  - `/post/<id>`
- Search:
  - `/search?q=<query>`
- Subreddit:
  - `/r/<subreddit>`
- User:
  - `/user/<username>`

### Nudeleted

**Primary URL**: [https://nudeleted.com](https://nudeleted.com)

**Supported Domains**: `nudeleted.*`

**Supported Paths**:

- Search:
  - `/search/...`
- Tags:
  - `/tags/...`
- Video:
  - `/videos/...`

### NudoStar

**Primary URL**: [https://nudostar.com/forum](https://nudostar.com/forum)

**Supported Domains**: `nudostar.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### NudoStarTV

**Primary URL**: [https://nudostar.tv](https://nudostar.tv)

**Supported Domains**: `nudostar.tv`

**Supported Paths**:

- Model:
  - `/models/...`

### OctaveMusic

**Primary URL**: [https://music.octavestreaming.com](https://music.octavestreaming.com)

**Supported Domains**: `music.octavestreaming`

**Supported Paths**:

- Album:
  - `/album/<album_id`
- Artist Albums:
  - `/artist/<artist_id>`
- Artist Top 50 songs:
  - `/artist/<artist_id>/top-songs`
- Track:
  - `/album/<album_id>?t=<track_id>`

### Odysee

**Primary URL**: [https://odysee.com](https://odysee.com)

**Supported Domains**: `odysee.*`

**Supported Paths**:

- Embed:
  - `/$/embed/@channel:uri`
- Video:
  - `/@channel:uri`

### ok.ru

**Primary URL**: [https://ok.ru](https://ok.ru)

**Supported Domains**: `odnoklassniki.ru`, `ok.ru`

**Supported Paths**:

- Channel:
  - `/profile/<username>/c<channel_id>`
  - `/video/c<channel_id>`
- Video:
  - `/video/<video_id>`

### OmegaScans

**Primary URL**: [https://omegascans.org](https://omegascans.org)

**Supported Domains**: `omegascans.*`

**Supported Paths**:

- Chapter:
  - `/series/<series_name>/<slug>`
- Direct links:
  - `/file/....`
- Series:
  - `/series/<series_name>`

### OneDrive

**Primary URL**: [https://onedrive.com](https://onedrive.com)

**Supported Domains**: `1drv.ms`, `onedrive.live.com`

**Supported Paths**:

- Access Link:
  - `https://onedrive.live.com/?authkey=<KEY>&id=<ID>&cid=<CID>`
- Share Link (anyone can access):
  - `https://1drv.ms/<path>`

### OnePace

**Primary URL**: [https://onepace.net](https://onepace.net)

**Supported Domains**: `onepace.net`

**Supported Paths**:

- All episodes:
  - `/watch`

### OnlyHaven

**Primary URL**: [https://cum.st](https://cum.st)

**Supported Domains**: `cum.st`

**Supported Paths**:

- Creator:
  - `/creators/<service>/<user_id>`
- DM:
  - `/creators/<service>/<user_id>/dm/<dm_id>`
- Post:
  - `/creators/<service>/<user_id>/post/<post_id>`
- Post Search:
  - `/search?q=...`

### OwnCloud

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Public Share:
  - `/s/<share_token>`

### Patreon

**Primary URL**: [https://www.patreon.com](https://www.patreon.com)

**Supported Domains**: `patreon.*`

**Supported Paths**:

- Creator:
  - `/<creator>`
  - `/cw/<creator>`
- Post:
  - `/<creator>/posts/<slug>-<post-id>`
  - `/posts/<slug>-<post-id>`

### Pawchive

**Primary URL**: [https://pawchive.pw](https://pawchive.pw)

**Supported Domains**: `pawchive.pw`, `pawchive.st`

**Supported Paths**:

- Creator:
  - `/<service>/user/<user_id>`
- Direct links:
  - `/data/...`
  - `/thumbnail/...`
- Favorites:
  - `/account/favorites/posts|artists`
  - `/favorites?type=post|artist`
- Post:
  - `/<service>/user/<user_id>/post/<post_id>`
- Revision:
  - `/<service>/user/<user_id>/post/<post_id>/revision/<revision_id>`
- Search:
  - `/search?q=...`

### pCloud

**Primary URL**: [https://www.pcloud.com](https://www.pcloud.com)

**Supported Domains**: `e.pc.cd`, `pc.cd`, `pcloud.*`

**Supported Paths**:

- Public File or folder:
  - `?code=<share_code>`
  - `e.pc.cd/<short_code>`
  - `u.pc.cd/<short_code>`

### Peertube

**Primary URL**: [https://joinpeertube.org](https://joinpeertube.org)

**Supported Domains**: `peertube.*`

**Supported Paths**:

- Account:
  - `/a/<username>/videos`
- Channel:
  - `/c/<channel_uuid>`
- Playlist:
  - `/w/p/<playlist_uuid>`
- Video:
  - `/videos/watch/<short_uuid>`
  - `/videos/watch/<video_uuid>`
  - `/w/<short_uuid>`
  - `/w/<video_uuid>`

### PeerTubeGeneric

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- Account:
  - `/a/<username>/videos`
- Channel:
  - `/c/<channel_uuid>`
- Playlist:
  - `/w/p/<playlist_uuid>`
- Video:
  - `/videos/watch/<short_uuid>`
  - `/videos/watch/<video_uuid>`
  - `/w/<short_uuid>`
  - `/w/<video_uuid>`

### PillowCase

**Primary URL**: [https://pillows.su](https://pillows.su)

**Supported Domains**: `pillowcase.su`, `pillows.su`

**Supported Paths**:

- File:
  - `/api/download/<file_uid>`
  - `/api/get/<file_uid>`
  - `/api/metadata/<file_uid>.txt`
  - `/f/<file_uid>`

### PimpAndHost

**Primary URL**: [https://pimpandhost.com](https://pimpandhost.com)

**Supported Domains**: `pimpandhost.*`

**Supported Paths**:

- Album:
  - `/album/...`
- Image:
  - `/image/...`

### PimpBunny

**Primary URL**: [https://pimpbunny.com](https://pimpbunny.com)

**Supported Domains**: `pimpbunny.com`

**Supported Paths**:

- Album:
  - `/albums/<album_name>`
- Category:
  - `/categories/<category>`
- Model Albums:
  - `/albums/models/<model_name>`
- Models:
  - `/onlyfans-models/<model_name>`
- Tag:
  - `/tags/<tag>`
- Videos:
  - `/videos/...`

### Pinterest

**Primary URL**: [https://www.pinterest.com](https://www.pinterest.com)

**Supported Domains**: `pinterest.*`

**Supported Paths**:

- Board:
  - `/<user>/<slug>`
- Pin:
  - `/pin/<pin_id>`
- User Boards:
  - `/<user>`

### PixelDrain

**Primary URL**: [https://pixeldrain.com](https://pixeldrain.com)

**Supported Domains**: `pixeldra.in`, `pixeldrain.biz`, `pixeldrain.com`, `pixeldrain.dev`, `pixeldrain.net`, `pixeldrain.nl`, `pixeldrain.tech`

**Supported Paths**:

- File:
  - `/api/file/<file_id>`
  - `/l/<list_id>#item=<file_index>`
  - `/u/<file_id>`
- Filesystem:
  - `/api/filesystem/<path>...`
  - `/d/<id>`
- Folder:
  - `/api/list/<list_id>`
  - `/l/<list_id>`

**Notes**

- text files will not be downloaded but their content will be parsed for URLs

### Pixeldrain-proxy

**Primary URL**: [https://pd.1drv.eu.org](https://pd.1drv.eu.org)

**Supported Domains**: `pd.1drv.eu.org`, `pd.cybar.xyz`

**Supported Paths**:

- File:
  - `/<file_id>`

### PixHost

**Primary URL**: [https://pixhost.cc](https://pixhost.cc)

**Supported Domains**: `pixhost.cc`, `pixhost.org`, `pixhost.to`

**Supported Paths**:

- Gallery:
  - `/gallery/<gallery_id>`
- Image:
  - `/show/<image_id>`
- Thumbnail:
  - `/thumbs/..`

### Pkmncards

**Primary URL**: [https://pkmncards.com](https://pkmncards.com)

**Supported Domains**: `pkmncards.*`

**Supported Paths**:

- Card:
  - `/card/...`
- Series:
  - `/series/...`
- Set:
  - `/set/...`

### Pluto.tv

**Primary URL**: [https://pluto.tv](https://pluto.tv)

**Supported Domains**: `pluto.tv`

**Supported Paths**:

- Episode:
  - `<region>/shows/<show_id>/episode/<episode_id>`
- Movie:
  - `/<region>/movies/<movie_id>`
- Show:
  - `<region>/shows/<show_slug>`
  - `<region>/shows/<show_slug>/season/<season>`

### PMVHaven

**Primary URL**: [https://pmvhaven.com](https://pmvhaven.com)

**Supported Domains**: `pmvhaven.*`

**Supported Paths**:

- Playlist:
  - `/playlists/<playlist_id>`
- Search results:
  - `/search?q=<query>`
- Users:
  - `/profile/<user_id>`
  - `/users/<user_id>`
- Video:
  - `/video/<video_name>_<video_id>`

### PornHub

**Primary URL**: [https://www.pornhub.com](https://www.pornhub.com)

**Supported Domains**: `pornhub.*`

**Supported Paths**:

- Album:
  - `/album/<album_id>`
- Channel:
  - `/channel/<name>`
- Gif:
  - `/gif/<gif_id>`
- Photo:
  - `/photo/<photo_id>`
- Playlist:
  - `/playlist/<playlist_id>`
- Profile:
  - `/model/<name>`
  - `/pornstar/<name>`
  - `/users/<name>`
- Profile albums:
  - `/model/<name>/photos`
  - `/pornstar/<name>/photos`
  - `/users/<name>/photos`
- Profile clips:
  - `/model/<name>/clips`
  - `/pornstar/<name>/clips`
  - `/users/<name>/clips`
- Profile gifs:
  - `/model/<name>/gifs`
  - `/pornstar/<name>/gifs`
  - `/users/<name>/gifs`
- Profile uploaded videos:
  - `/model/<name>/videos/upload`
  - `/pornstar/<name>/videos/upload`
  - `/users/<name>/videos/upload`
- Profile videos:
  - `/model/<name>/videos`
  - `/pornstar/<name>/videos`
  - `/users/<name>/videos`
- Video:
  - `/embed/<video_id>`
  - `/view_video.php?viewkey=<video_id>`

### PornPics

**Primary URL**: [https://pornpics.com](https://pornpics.com)

**Supported Domains**: `pornpics.*`

**Supported Paths**:

- Categories:
  - `/categories/....`
- Channels:
  - `/channels/...`
- Direct Links:
- Gallery:
  - `/galleries/...`
- Pornstars:
  - `/pornstars/...`
- Search:
  - `/?q=<query>`
- Tags:
  - `/tags/...`

### Porntrex

**Primary URL**: [https://www.porntrex.com](https://www.porntrex.com)

**Supported Domains**: `porntrex.*`

**Supported Paths**:

- Album:
  - `/albums/...`
- Category:
  - `/categories/...`
- Model:
  - `/models/...`
- Playlist:
  - `/playlists/...`
- Search:
  - `/search/...`
- Tag:
  - `/tags/...`
- User:
  - `/members/...`
- Video:
  - `/video/...`

### PornZog

**Primary URL**: [https://pornzog.com](https://pornzog.com)

**Supported Domains**: `pornzog.*`

**Supported Paths**:

- Video:
  - `/video/...`

### PostImg

**Primary URL**: [https://postimg.cc](https://postimg.cc)

**Supported Domains**: `postimages.org`, `postimg.cc`, `postimg.org`

**Supported Paths**:

- Album:
  - `/gallery/<album_id>/...`
- Direct links:
  - `i.postimg.cc/<image_id>/...`
- Image:
  - `/<image_id>/...`

### RealBooru

**Primary URL**: [https://realbooru.com](https://realbooru.com)

**Supported Domains**: `realbooru.*`

**Supported Paths**:

- File:
  - `?id=<file_id>`
- Tags:
  - `?tags=<name>`

### RealDebrid

**Primary URL**: [https://real-debrid.com](https://real-debrid.com)

**Supported Domains**: `real-debrid.*`

**Supported Paths**:

### RedGifs

**Primary URL**: [https://www.redgifs.com](https://www.redgifs.com)

**Supported Domains**: `redgifs.*`

**Supported Paths**:

- Embeds:
  - `/ifr/<gif_id>`
- Gif:
  - `/watch/<gif_id>`
- Image:
  - `/i/<image_id>`
- User:
  - `/users/<user>`

### Redtube

**Primary URL**: [https://www.redtube.com](https://www.redtube.com)

**Supported Domains**: `redtube.*`

**Supported Paths**:

- Video:
- `/<video_id>`
- `?id=<video_id>`

### Rootz.so

**Primary URL**: [https://www.rootz.so](https://www.rootz.so)

**Supported Domains**: `rootz.so`

**Supported Paths**:

- File:
  - `/d/<file_id>`
  - `/file/<file_id>`

### Rule34Vault

**Primary URL**: [https://rule34vault.com](https://rule34vault.com)

**Supported Domains**: `rule34vault.*`

**Supported Paths**:

- Playlist:
  - `/playlists/view/<playlist_id>`
- Post:
  - `/post/<post_id>`
- Tags:
  - `/<tag1>|<tags2>...`

### Rule34Video

**Primary URL**: [https://rule34video.com](https://rule34video.com)

**Supported Domains**: `rule34video.*`

**Supported Paths**:

- Category:
  - `/categories/<name>`
- Members:
  - `/members/<member_id>`
- Model:
  - `/models/<name>`
- Search:
  - `/search/<query>`
- Tag:
  - `/tags/<name>`
- Video:
  - `/video/<id>/<slug>`

### Rule34XXX

**Primary URL**: [https://rule34.xxx](https://rule34.xxx)

**Supported Domains**: `rule34.xxx`

**Supported Paths**:

- File:
  - `?id=...`
- Tag:
  - `?tags=...`

### Rule34XYZ

**Primary URL**: [https://rule34.xyz](https://rule34.xyz)

**Supported Domains**: `rule34.xyz`

**Supported Paths**:

- Playlist:
  - `/playlists/view/<playlist_id>`
- Post:
  - `/post/<post_id>`
- Tags:
  - `/<tag1>|<tags2>...`

### Rumble

**Primary URL**: [https://rumble.com](https://rumble.com)

**Supported Domains**: `rumble.*`

**Supported Paths**:

- Channel:
  - `/c/<name>`
- Embed:
  - `/embed/<video_id>`
- User:
  - `/user/<name>`
- Video:
  - `<video_id>-<video-title>.html`

### Rutube

**Primary URL**: [https://rutube.ru](https://rutube.ru)

**Supported Domains**: `rutube.*`

**Supported Paths**:

- Video:
  - `/play/embed/<id>`
  - `/video/<id>`

### Scrolller

**Primary URL**: [https://scrolller.com](https://scrolller.com)

**Supported Domains**: `scrolller.*`

**Supported Paths**:

- Subreddit:
  - `/r/<subreddit>`

### SendNow

**Primary URL**: [https://send.now](https://send.now)

**Supported Domains**: `send.now`

**Supported Paths**:

- Direct Links:

### SendVid

**Primary URL**: [https://sendvid.com](https://sendvid.com)

**Supported Domains**: `sendvid.*`

**Supported Paths**:

- Direct Links:
- Embeds:
  - `/embed/...`
- Videos:
  - `/...`

### Sex.com

**Primary URL**: [https://sex.com](https://sex.com)

**Supported Domains**: `sex.com`

**Supported Paths**:

- Shorts Profiles:
  - `/shorts/<profile>`

### SocialMediaGirls

**Primary URL**: [https://forums.socialmediagirls.com](https://forums.socialmediagirls.com)

**Supported Domains**: `socialmediagirls.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### Soundgasm

**Primary URL**: [https://soundgasm.net](https://soundgasm.net)

**Supported Domains**: `soundgasm.*`

**Supported Paths**:

- Audio:
  - `/u/<user>/<slug>`
- User:
  - `/u/<user>`

### SpankBang

**Primary URL**: [https://spankbang.com](https://spankbang.com)

**Supported Domains**: `spankbang.*`

**Supported Paths**:

- Playlist:
  - `/<playlist_id>/playlist/...`
- Profile:
  - `/profile/<user>`
  - `/profile/<user>/videos`
- Video:
  - `/<video_id>/embed`
  - `/<video_id>/video`
  - `/play/<video_id>`
  - `<playlist_id>-<video_id>/playlist/...`

### Streamable

**Primary URL**: [https://streamable.com](https://streamable.com)

**Supported Domains**: `streamable.*`

**Supported Paths**:

- Video:
  - `/...`

### Streamtape

**Primary URL**: [https://streamtape.com](https://streamtape.com)

**Supported Domains**: `streamtape.com`

**Supported Paths**:

- Player:
  - `/e/<video_id>`
- Videos:
  - `/v/<video_id>`

### Suvobox

**Primary URL**: [https://www.suvobox.com](https://www.suvobox.com)

**Supported Domains**: `suvobox.*`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Direct File:
  - `/d/<file_id>.<ext>`
  - `/m/<file_id>-medium.<ext>`
- File:
  - `/f/<file_id>`

### T.co

**Primary URL**: [https://t.co](https://t.co)

**Supported Domains**: `t.co`

**Supported Paths**:

- Redirect:
  - `t.co/<short_code>`

### TabooTube

**Primary URL**: [https://www.tabootube.xxx](https://www.tabootube.xxx)

**Supported Domains**: `tabootube.*`

**Supported Paths**:

- Video:
  - `/video/...`

### ThisVid

**Primary URL**: [https://thisvid.com](https://thisvid.com)

**Supported Domains**: `thisvid.*`

**Supported Paths**:

- Albums:
  - `/albums/<album_name>`
- Categories:
  - `/categories/<name>`
- Image:
  - `/albums/<album_name>/<image_name>`
- Members:
  - `/members/<member_id>`
- Search:
  - `/search/?q=<query>`
- Tags:
  - `/tags/<name>`
- Videos:
  - `/videos/<slug>`

### ThotHub

**Primary URL**: [https://thothub.to](https://thothub.to)

**Supported Domains**: `thothub.*`

**Supported Paths**:

- Album:
  - `/albums/<id>/<name>`
- Image:
  - `/get_image/...`
- Video:
  - `/videos/<id>/<slug>`

### TikTok

**Primary URL**: [https://www.tiktok.com](https://www.tiktok.com)

**Supported Domains**: `tiktok.*`

**Supported Paths**:

- Photo:
  - `/@/photo/<photo_id>`
  - `/@<user>/photo/<photo_id>`
  - `/share/photo/<photo_id>`
- User:
  - `/@<user>`
- Video:
  - `/@/video/<video_id>`
  - `/@<user>/video/<video_id>`
  - `/share/video/<video_id>`

### TitsInTops

**Primary URL**: [https://titsintops.com/phpBB2](https://titsintops.com/phpBB2)

**Supported Domains**: `titsintops.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### TNAFlix

**Primary URL**: [https://www.tnaflix.com](https://www.tnaflix.com)

**Supported Domains**: `tnaflix.*`

**Supported Paths**:

- Channel:
  - `/channel/...`
- Profile:
  - `/profile/...`
- Search:
  - `/search?what=<query>`
- Video:
  - `/<category>/<title>/video<video_id>`

### Tokyomotion

**Primary URL**: [https://www.tokyomotion.net](https://www.tokyomotion.net)

**Supported Domains**: `tokyomotion.*`

**Supported Paths**:

- Albums:
  - `/album/<album_id>`
  - `/user/<user>/albums/`
- Photo:
  - `/photo/<photo_id>`
  - `/user/<user>/favorite/photos`
- Playlist:
  - `/user/<user>/favorite/videos`
- Profiles:
  - `/user/<user>`
- Search Results:
  - `/search?...`
- Video:
  - `/video/<video_id>`

### Toonily

**Primary URL**: [https://toonily.com](https://toonily.com)

**Supported Domains**: `toonily.*`

**Supported Paths**:

- Chapter:
  - `/serie/<name>/chapter-<chapter-id>`
- Series:
  - `/serie/<name>`

### Tranny.One

**Primary URL**: [https://www.tranny.one](https://www.tranny.one)

**Supported Domains**: `tranny.one`

**Supported Paths**:

- Album:
  - `/pics/album/<album_id>`
- Pornstars:
  - `/pornstar/<model_id>/<model_name>`
- Search:
  - `/search/<search_query>`
- Video:
  - `/view/<video_id>`

### TrannyGem

**Primary URL**: [https://www.trannygem.com](https://www.trannygem.com)

**Supported Domains**: `trannygem.*`

**Supported Paths**:

- Albums:
  - `/albums/<album_name>`
- Categories:
  - `/categories/<name>`
- Image:
  - `/albums/<album_name>/<image_name>`
- Members:
  - `/members/<member_id>`
- Search:
  - `/search/?q=<query>`
- Tags:
  - `/tags/<name>`
- Videos:
  - `/videos/<slug>`

### Transfer.it

**Primary URL**: [https://transfer.it](https://transfer.it)

**Supported Domains**: `transfer.it`

**Supported Paths**:

- Transfer:
  - `/t/<transfer_id>`

### TransFlix

**Primary URL**: [https://transflix.net](https://transflix.net)

**Supported Domains**: `transflix.*`

**Supported Paths**:

- Search:
  - `/search/?q=<query>`
- Video:
  - `/video/<name>-<video_id>`

### TubePornClassic

**Primary URL**: [https://tubepornclassic.com](https://tubepornclassic.com)

**Supported Domains**: `tubepornclassic.com`, `tubepornclassic.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### TurboVid

**Primary URL**: [https://turbo.cr](https://turbo.cr)

**Supported Domains**: `saint.to`, `saint2.cr`, `saint2.su`, `turbo.cr`, `turbovid.cr`

**Supported Paths**:

- Album:
  - `/a/<album_id>`
- Direct links:
  - `/data/<file_id>.mp4`
- Search:
  - `library?q=<query>`
- Video:
  - `/d/<file_id>`
  - `/embed/<file_id>`
  - `/v/<file_id>`

### Twitch

**Primary URL**: [https://www.twitch.tv](https://www.twitch.tv)

**Supported Domains**: `twitch.*`

**Supported Paths**:

- Clip:
  - `/<user>/clip/<slug>`
  - `/embed?clip=<slug>`
  - `https://clips.twitch.tv/<slug>`
- Collection:
  - `/collections/<collection_id>`
- VOD:
  - `/<user>/v/<vod_id>`
  - `/video/<vod_id>`
  - `/videos/<vod_id>`
  - `?video=<vod_id>`

### Twitter

**Primary URL**: [https://x.com](https://x.com)

**Supported Domains**: `twitter.com`, `x.com`

**Supported Paths**:

- Broadcast:
  - `/i/broadcasts/<broadcast_id>`
  - `/i/events/<event_id>`
- Search:
  - `/search?q=<query>`
  - `/search?q=<query>&f=latest`
  - `/search?q=<query>&f=media`
  - `/search?q=<query>&f=top`
- Tweet/Thread/Article:
  - `/<user_handle>/status/<status_id>`
  - `/i/web/status/<status_id>`
- User media:
  - `/<user_handle>/media`
- User tweets:
  - `/<user_handle>`

### TwitterImages

**Primary URL**: [https://twimg.com](https://twimg.com)

**Supported Domains**: `twimg.*`

**Supported Paths**:

- Photo:
  - `/media/<media_id>...`
- Video:
  - `/amplify_video/<media_id>...`

### TWPornStars

**Primary URL**: [https://www.twpornstars.com](https://www.twpornstars.com)

**Supported Domains**: `indiantw.com`, `twanal.com`, `twgaymuscle.com`, `twgays.com`, `twlesbian.com`, `twmilf.com`, `twonfans.com`, `twpornstars.com`, `twteens.com`, `twtiktoks.com`

**Supported Paths**:

- Collection/User:
  - `/<name>`
- Hashtag:
  - `/hashtag/<hashtags>`
- Post:
  - `/p/<post_id>`

### TXXX

**Primary URL**: [https://txxx.com](https://txxx.com)

**Supported Domains**: `txxx.com`, `txxx.tube`, `videotxxx.com`, `videotxxx.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Upload.ee

**Primary URL**: [https://www.upload.ee](https://www.upload.ee)

**Supported Domains**: `upload.ee`

**Supported Paths**:

- File:
  - `/files/<file_id>`

### UPornia

**Primary URL**: [https://upornia.com](https://upornia.com)

**Supported Domains**: `upornia.com`, `upornia.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Vidara

**Primary URL**: [https://vidara.to](https://vidara.to)

**Supported Domains**: `stmix.io`, `streamix.so`, `vidara.so`, `vidara.to`, `xca.cymru`

**Supported Paths**:

- Video:
  - `/e/<video_id>`

### Vidstack

**Primary URL**: [https://videosh.upns.live](https://videosh.upns.live)

**Supported Domains**: `videosh.upns.live`, `vidstack.io`

**Supported Paths**:

- Video:
  - `/#<video_id>`

### ViperGirls

**Primary URL**: [https://vipergirls.to](https://vipergirls.to)

**Supported Domains**: `viper.click`, `vipergirls.to`

**Supported Paths**:

- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/threads/<thread_name>`

### Vipr.im

**Primary URL**: [https://vipr.im](https://vipr.im)

**Supported Domains**: `vipr.im`

**Supported Paths**:

- Direct Image:
  - `/i/.../<slug>`
- Image:
  - `/<id>`
- Thumbnail:
  - `/th/.../<slug>`

### VJav

**Primary URL**: [https://vjav.com](https://vjav.com)

**Supported Domains**: `vjav.com`, `vjav.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Voe.sx

**Primary URL**: [https://voe.sx](https://voe.sx)

**Supported Domains**: `alejandrocenturyoil.com`, `diananatureforeign.com`, `heatherwholeinvolve.com`, `jennifercertaindevelopment.com`, `jilliandescribecompany.com`, `jonathansociallike.com`, `mariatheserepublican.com`, `maxfinishseveral.com`, `nathanfromsubject.com`, `richardsignfish.com`, `robertordercharacter.com`, `sarahnewspaperbeat.com`, `voe.sx`

**Supported Paths**:

- Embed:
  - `/e/video_id`

### VoyeurHit

**Primary URL**: [https://voyeurhit.com](https://voyeurhit.com)

**Supported Domains**: `voyeurhit.com`, `voyeurhit.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### VSCO

**Primary URL**: [https://vsco.co](https://vsco.co)

**Supported Domains**: `vsco.*`

**Supported Paths**:

- Gallery:
  - `/<user>/gallery`
- Media:
  - `/<user>/media/<media_id>`
  - `/<user>/video/<media_id>`

### VXXX

**Primary URL**: [https://vxxx.com](https://vxxx.com)

**Supported Domains**: `vxxx.com`, `vxxx.tube`

**Supported Paths**:

- Video:
  - `/video-<video-id>`

### Webmshare

**Primary URL**: [https://webmshare.com](https://webmshare.com)

**Supported Domains**: `webmshare.*`

**Supported Paths**:

- Search:
  - `/results?q=<query>`
- Video:
  - `/<video_id>`
  - `/download-webm/<video_id>`
  - `/play/<video_id>`

### WeTransfer

**Primary URL**: [https://wetransfer.com](https://wetransfer.com)

**Supported Domains**: `we.tl`, `wetransfer.com`

**Supported Paths**:

- Direct links:
  - `download.wetransfer.com/...`
- Public link:
  - `wetransfer.com/downloads/<file_id>/<security_hash>`
- Share Link:
  - `wetransfer.com/downloads/<file_id>/<recipient_id>/<security_hash>`
- Short Link:
  - `we.tl/<short_file_id>`

### Whyp.it

**Primary URL**: [https://whyp.it](https://whyp.it)

**Supported Domains**: `whyp.it`

**Supported Paths**:

- Audio:
  - `/tracks/<slug>-<id>`
- Collection:
  - `/collections/<slug>-<id>`
- User:
  - `/users/<slug>-<id>`

### Wikifeet

**Primary URL**: [https://wikifeet.com](https://wikifeet.com)

**Supported Domains**: `wikifeet.*`

**Supported Paths**:

- Celeb:
  - `/<name>`

### Wikifeet Men

**Primary URL**: [https://men.wikifeet.com](https://men.wikifeet.com)

**Supported Domains**: `men.wikifeet`

**Supported Paths**:

- Celeb:
  - `/<name>`

### Wikifeet X

**Primary URL**: [https://wikifeetx.com](https://wikifeetx.com)

**Supported Domains**: `wikifeetx.*`

**Supported Paths**:

- Celeb:
  - `/<name>`

### WordPressHTML

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- All Posts:
  - `/posts/`
- Category:
  - `/category/<category_slug>`
- Post:
  - `/<post_slug>/`
- Tag:
  - `/tag/<tag_slug>`

### WordPressMedia

**Primary URL**: [::GENERIC CRAWLER::](::GENERIC CRAWLER::)

**Supported Domains**:

**Supported Paths**:

- All Posts:
  - `/posts/`
- Category:
  - `/category/<category_slug>`
- Post:
  - `/<post_slug>/`
- Tag:
  - `/tag/<tag_slug>`

### Xasiat

**Primary URL**: [https://www.xasiat.com](https://www.xasiat.com)

**Supported Domains**: `xasiat.*`

**Supported Paths**:

- Album:
  - `/albums/<id>/<name>`
- Images:
  - `/get_image/...`
- Videos:
  - `/videos/<id>/<name>`

### XBunker

**Primary URL**: [https://xbunker.cc](https://xbunker.cc)

**Supported Domains**: `xbunker.*`

**Supported Paths**:

- Attachments:
  - `/attachments|data|uploads/...`
- Threads:
  - `/goto/<post_id>`
  - `/posts/<post_id>`
  - `/thread|topic|tema|threads|topics|temas/<thread_name_and_id>`

**Notes**

- base crawler: Xenforo

### XGroovy

**Primary URL**: [https://xgroovy.com](https://xgroovy.com)

**Supported Domains**: `xgroovy.*`

**Supported Paths**:

- Channel:
  - `/<category>/channels/...`
  - `/channels/...`
- Gif:
  - `/<category>/gifs/<gif_id>/...`
  - `/gifs/<gif_id>/...`
- Images:
  - `/<category>/photos/<photo_id>/...`
  - `/photos/<photo_id>/...`
- Pornstar:
  - `/<category>/pornstars/<pornstar_id>/...`
  - `/pornstars/<pornstar_id>/...`
- Search:
  - `/<category>/search/...`
  - `/search/...`
- Tag:
  - `/<category>/tags/...`
  - `/tags/...`
- Video:
  - `/<category>/videos/<video_id>/...`
  - `/videos/<video_id>/...`

### xHamster

**Primary URL**: [https://xhamster.com](https://xhamster.com)

**Supported Domains**: `xhamster.*`

**Supported Paths**:

- Creator:
  - `/creators/<creator_name>`
- Creator Galleries:
  - `/creators/<creator_name>/photos`
- Creator Videos:
  - `/creators/<creator_name>/exclusive`
- Gallery:
  - `/photos/gallery/<gallery_name_or_id>`
- User:
  - `/users/<user_name>`
  - `/users/profiles/<user_name>`
- User Galleries:
  - `/users/<user_name>/photos`
- User Videos:
  - `/users/<user_name>/videos`
- Video:
  - `/shorts/<slug>-<video_id>`
  - `/videos/<slug>-<video_id>`

### XMegaDrive

**Primary URL**: [https://www.xmegadrive.com](https://www.xmegadrive.com)

**Supported Domains**: `xmegadrive.*`

**Supported Paths**:

- Albums:
  - `/albums/<album_name>`
- Categories:
  - `/categories/<name>`
- Image:
  - `/albums/<album_name>/<image_name>`
- Members:
  - `/members/<member_id>`
- Search:
  - `/search/?q=<query>`
- Tags:
  - `/tags/<name>`
- Videos:
  - `/videos/<slug>`

### XMilf

**Primary URL**: [https://xmilf.com](https://xmilf.com)

**Supported Domains**: `xmilf.com`, `xmilf.tube`

**Supported Paths**:

- Video:
  - `/embed/<video_id>/...`
  - `/videos/<video_id>/...`

### Xpornium

**Primary URL**: [https://xpornium.net](https://xpornium.net)

**Supported Domains**: `xpornium.*`

**Supported Paths**:

- Video:
  - `/embed/<video_id>`

### xVideos

**Primary URL**: [https://www.xvideos.com](https://www.xvideos.com)

**Supported Domains**: `xv-ru.com`, `xvideos-ar.com`, `xvideos-india.com`, `xvideos.com`, `xvideos.es`

**Supported Paths**:

- Account:
  - `/<channel_name>`
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles/<name>`
- Account Photos:
  - `/<channel_name>#_tabPhotos`
  - `/<channel_name>/photos/...`
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles/<name>#_tabPhotos`
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles/<name>/photos/...`
- Account Quickies:
  - `/<channel_name>#quickies`
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles/<name>#quickies`
- Account Videos:
  - `/<channel_name>#_tabVideos`
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles/<name>#_tabVideos`
- Video:
  - `/amateur|amateur-channels|amateurs|channel|channel-channels|channels|pornstar|pornstar-channels|pornstars|profile|profile-channels|profiles#quickies/(a|h|v)/<video_id>`
  - `/video.<encoded_id>/<title>`
  - `/video<id>/<title>`

### XXXBunker

**Primary URL**: [https://xxxbunker.com](https://xxxbunker.com)

**Supported Domains**: `xxxbunker.*`

**Supported Paths**:

- Category:
  - `/categories/<category>`
- Search:
  - `/search/<video_id>`
- User Favorites:
  - `/<username>/favoritevideos`
- Video:
  - `/<video_id>`

### YandexDisk

**Primary URL**: [https://disk.yandex.com.tr](https://disk.yandex.com.tr)

**Supported Domains**: `disk.yandex`, `yadi.sk`

**Supported Paths**:

- File:
  - `/d/<folder_id>/<file_name>`
  - `/i/<file_id>`
- Folder:
  - `/d/<folder_id>`

**Notes**

- Does NOT support nested folders

### YouJizz

**Primary URL**: [https://www.youjizz.com](https://www.youjizz.com)

**Supported Domains**: `youjizz.*`

**Supported Paths**:

- Video:
  - `/videos/<video_name>`
  - `/videos/embed/<video_id>`

### YourLesbians

**Primary URL**: [https://yourlesbians.com](https://yourlesbians.com)

**Supported Domains**: `yourlesbians.com`

**Supported Paths**:

- Albums:
  - `/albums/<album_name>`
- Categories:
  - `/categories/<name>`
- Image:
  - `/albums/<album_name>/<image_name>`
- Members:
  - `/members/<member_id>`
- Search:
  - `/search/?q=<query>`
- Tags:
  - `/tags/<name>`
- Videos:
  - `/videos/<slug>`

### YTboob

**Primary URL**: [https://ytboob.com](https://ytboob.com)

**Supported Domains**: `ytboob.com`

**Supported Paths**:

- Video:
  - `/video/<slug>`

### Yurivan

**Primary URL**: [https://www.yurivan.com](https://www.yurivan.com)

**Supported Domains**: `yurivan.*`

**Supported Paths**:

- Chapter:
  - `/story/<story_id>/read?chapter<chapter_id>`
- Story:
  - `/story/<story_id>`
- Video:
  - `/story/<story_id>/chapter/1`

<!-- END_SUPPORTED_SITES -->
