---
description: These are the websites supported by Cyberdrop-DL
icon: globe-pointer
---

# Supported Websites

## Content Hosts
| Domain          | Supported URL Paths |
|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Bunkrr          | Albums: `/a/...` <br> Videos: `/v/...` <br> Others: `/f/...` <br> Direct links |
| Coomer          | Fansly Model: `/fansly/user/<user>` <br> Favorites: `/favorites` <br> Search: `/search?...` <br> Individual Post: `/<service>/user/<user>/post/<post_id>` <br> OnlyFans Model: `/onlyfans/user/<user>` <br> Direct links |
| Comics.8muses.com | Album: `/comics/album/...` |
| Cyberdrop       | Albums: `/a/...` <br> Files: `/f/...` <br> Direct links |
| Cyberfile       | Files: `/...` <br> Folders: `/folder/...` <br> Shared: `/shared/...` |
| E-Hentai        | Albums: `/g/...` <br> Files: `/s/...` |
| Erome           | Album: `/a/...` <br> Profile: `/...`  |
| Fapello         | Individual Post: `/.../...` <br> Model: `/...` |
| GoFile          | Album: `/d/...`|
| HotPic          | Album: `/album/...` <br> Image: `/i/...`|
| ImageBam        | Album: `/view/...` <br> Image: `/view/...` <br> Direct links |
| ibb imgbb       | Album: `/album/...` <br> Image: `/...`|
| Iceyfile.com    | Files: `/...` <br> Folders: `/folder/...` <br> Shared: `/shared/...` |
| ImgBox          | Album: `/g/...` <br> Images: `/...` <br> Direct links |
| Img.kiwi        | Album: `/album/...` <br> Image: `/image/...` <br> Direct links  |
| Imgur           | Album: `/a/...` <br> Gallery: `/gallery/...` <br> Image: `/...` <br> Direct links |
| JPG.Church <br> JPG.Homes <br> JPG.Pet <br> JPEG.Pet <br> JPG1.Su <br> JPG2.Su <br> JPG3.Su <br> JPG4.Su <br> JPG5.Su | Album: `/a/...` <br> Image: `/img/...` <br> Direct links  |
| Imagepond.net   | Album: `/a/...` <br> Image: `/img/...` <br> Video: `/video/..`  <br> Direct links  |
| Kemono          | Afdian Model: `/afdian/user/<user>` <br> Boosty Model: `/boosty/user/<user>` <br> DLSite Model: `/dlsite/user/<user>` <br> Discord Server Channel: `/discord/server/...#...` <br> FanBox Model: `/fanbox/user/<user>` <br> Fantia Model: `/fantia/user/<user>` <br> Gumroad Model: `/gumroad/user/<user>` <br> Individual Post: `/<service>/user/<user>/post/<post_id>` <br> Patreon Model: `/patreon/user/<user>` <br> Search: `/search?...` <br> SubscribeStar Model: `/subscribestar/user/<user>` <br> Direct Links |
| Members.luscious.net        | Album: `/albums/...` |
| MediaFire       | File: `/file/...` <br>Folder: `/folder/...`|
| Nekohouse.su    | Fanbox Model: `/fanbox/user/<user>` <br> Fantia Model: `/fantia/user/<user>` <br> Fantia Products Model: `/fantia_products/user/<user>` <br> Individual Post: `/service/user/<user>/post/...` <br> Subscribestar Model: `/subscribestar/user/<user>` <br> Twitter Model: `/twitter/user/<user>` <br> Direct Links |
| Nudostar.TV     | Model: `/models/...`|
| OmegaScans      | Chapter: `/series/.../...` <br> Series: `/series/...` <br> Direct links |
| PimpAndHost     | Album: `/album/...` <br> Image: `/image/...`|
| PixHost.to      | Gallery: `/gallery/...` <br> Image: `/show/...` |
| PixelDrain      | File: `/u/...` <br> Folder: `/l/...` |
| PornPics.com    | Categories `/categories/....` <br> Channels  `/channels/...` <br> Gallery `/galleries/...` <br> Pornstars `/pornstars/...` <br> Search  `/?q=<query>` <br> Tags `/tags/...` <br> Direct Links |
| PostImg         | Album: `/gallery/...` <br> Image: `/...` <br> Direct links |
| RealBooru       | File page (id query) <br> Tags (tags query) |
| RedGifs         | User: `/users/<user>` <br> Video: `/watch/...` |
| Rule34Vault     | File page: `/post/...` <br> Playlist: `/playlists/view/...` <br> Tag: `/...` |
| Rule34.XXX      | File page (id query) <br> Tags (tags query) |
| Rule34.XYZ      | File page: `/post/...` <br> Tag: `/...` |
| Saint           | Albums: `/a/...` <br> Video: `/embed/...`, `/d/...` <br> Direct links |
| SendVid.com     | Videos: `/...` <br> Embeds: `/embed/...` <br> Direct Links |
| Scrolller       | Subreddit: `/r/...` |
| TikTok          | User: `/@<user>` <br> Video: `/@<user>/video/<video_id>` <br> Photo: `/@<user>/photo/<photo_id>` <br> |
| Toonily         | Chapter: `/webtoon/.../...` <br> Webtoon: `/webtoon/...` <br> Direct links  |
| Tokyomotion.net | Albums: `/user/<user>/albums/` , `/album/<album_id>` <br> Photo: `/photo/<photo_id>` , `/user/<user>/favorite/photos` <br> Playlist: `/user/<user>/favorite/videos` <br> Profiles: `/user/<user>` <br> Search Results: `/search?...` <br> Video: `/video/<video_id>` |
| XBunkr          | Albums: `/a/...` <br> Direct Links|
| XXXBunker       | Video: `/<video_id>` <br> Search Results: `/search/...`                            |


### Password Protected Content Hosts

Cyberdrop-DL can download password protected files and folders from these hosts. User must include the password as a query parameter in the input URL, adding `?password=<URL_PASSWORD>` to it.

Example: `https://cyberfile.me/folder/xUGg?password=1234`

| Domain |
| ------------------------------------------- |
| GoFile |
| Cyberfile                                   |
| Chevereto Sites (`jpg5`, `imagepond` or `img.kiwi`) |
| Iceyfile.com   |

### Additional Content Hosts with Real-Debrid

Cyberdrop-DL has integration with Real-Debrid as download service to support additional hosts. In order to enable Real-Debrid, user must provide their API token inside the `authentication.yaml` file. You can get your API token from this URL (you must be logged in): [https://real-debrid.com/apitoken](https://real-debrid.com/apitoken)

Supported domains via Real-Debrid include `mega.nz`, `rapidgator`, `google drive`, `1fichier`, `k2s`, `etc`. List of all supported domains can be found here (250+): [https://api.real-debrid.com/rest/1.0/hosts/domains](https://api.real-debrid.com/rest/1.0/hosts/domains)

## Forums

| Domain                      | Supported URL Paths  |
| --------------------------- | -------------------- |
| Bellazon.com                | Threads: `/main/topic/<thread_name>` |
| CelebForum                  | Threads: `/threads/<thread_name>`|
| F95Zone                     | Threads: `/threads/<thread_name>`|
| Forums.AllPornComix.com     | Threads: `/threads/<thread_name>`|
| Forums.SocialMediaGirls.com | Threads: `/threads/<thread_name>`|
| LeakedModels                | Threads: `/forum/threads/<thread_name>`|
| Nudostar                    | Threads: `/forum/threads/<thread_name>`|
| Reddit                      | User: `/user/<user>`, `/user/<user>/...` , `/u/<user>` <br> Subreddit: `/r/<subreddit>` <br> Direct Links |
| TitsInTops.com              | Threads: `/forum/threads/<thread_name>`|
| XBunker                     | Threads: `/threads/<thread_name>`|
