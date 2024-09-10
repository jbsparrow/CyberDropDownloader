---
description: These are all of the configuration options for Settings.
---

# Settings

<details>

<summary>Download Options</summary>

* block\_download\_sub\_folders

when this is set to true (or selected) downloads that would be in a folder structure like:

`Downloads/ABC/DEF/GHI/image.jpg`

will be changed to:

`Downloads/ABC/image.jpg`

***

* disable\_download\_attempts

By default the program will retry a download 10 times. You can customize this, or set this to true (or selected) to disable it and retry links until they complete.

However, to make sure the program will not run endlessly, there are certain situations where a file will never be retried, like if the program receives a 404 HTTP status, meaning the link is dead.

***

* disable\_file\_timestamps

By default the program will do it's absolute best to try and find when a file was uploaded. It'll then set the last modified/last accessed/created times on the file to match.

Setting this to true (or selecting it) will disable this function, and those times will be the time they were downloaded.

***

* include\_album\_id\_in\_folder\_name

Setting this to true (or selecting it) will include the album ID (random alphanumeric string) of the album in the download folder name.

***

* include\_thread\_id\_in\_folder\_name

Setting this to true (or selecting it) will include the thread ID (random alphanumeric string) of the album in the download folder name.

***

* remove\_domains\_from\_folder\_names

Setting this to true will remove the "(DOMAIN)" portion of folder names on new downloads.

***

* remove\_generated\_id\_from\_filenames

Setting this to true (or selecting it) will remove the alphanumeric ID added to the end of filenames on some websites (ex. Bunkrr).

***

* scrape\_single\_forum\_post

Setting this to true will result in only a single forum post being scraped on the given link.

***

* separate\_posts

Setting this to true (or selecting it) will separate content from forum posts into separate folders.

***

* skip\_download\_mark\_complete

Setting this to true (or selecting it) will skip downloading files and mark them as downloaded in the database.

</details>

<details>

<summary>Files</summary>

* input\_file

The path to the URLs.txt file you want to use for the config.

***

* download\_folder

The path to the location you want Cyberdrop-DL to download files to.

</details>

<details>

<summary>Logs</summary>

* log\_folder

The path to the location you want Cyberdrop-DL to store logs in.

***

* main\_log\_filename

What you want Cyberdrop-DL to call the main log file.

***

* last\_forum\_post\_filename

What you want Cyberdrop-DL to call the forum-post log file.

Cyberdrop-DL will store the link to the last forum posts it scraped from a given forum thread in this file.

***

* unsupported\_urls\_filename

What you want Cyberdrop-DL to call the unsupported log file.

Cyberdrop-DL will output links it can't download to this file.

***

* download\_error\_urls\_filename

What you want Cyberdrop-DL to call the download error log.

Cyberdrop-DL will output the links it fails to download, and the reason in CSV format.

***

* scrape\_error\_urls\_filename

What you want Cyberdrop-DL to call the scrape error log.

Cyberdrop-DL will output the links it fails to scrape, and the reason in CSV format.

</details>

<details>

<summary>File Size Limits</summary>

You can provide the maximum and minimum file size for each file "type".

This value is in bytes.

1 kb = 1024 bytes

1 mb = 1048576 bytes

1 gb = 1073741824 bytes

***

* maximum\_image\_filesize
* minimum\_image\_filesize
* maximum\_video\_filesize
* minimum\_video\_filesize
* maximum\_other\_filesize
* minimum\_other\_filesize

</details>

<details>

<summary>Ignore Options</summary>

Cyberdrop-DL comes equipped to ignore various files

***

* exclude\_videos

When this is set to true (or selected) the program will skip downloading video files.

***

* exclude\_images

When this is set to true (or selected) the program will skip downloading image files.

***

* exclude\_audio

When this is set to true (or selected) the program will skip downloading audio files.

***

* exclude\_other

When this is set to true (or selected) the program will skip downloading other files.

***

* ignore\_coomer\_ads

When this is set to true, the program will skip past ads posted by models in coomer profiles.

***

* skip\_hosts

You can supply hosts that you'd like the program to skip past, and not scrape/download from.

Options:

"bunkrr", "celebforum", "coomer", "cyberdrop", "cyberfile", "e-hentai", "erome", "fapello", "f95zone", "gofile", "hotpic", "ibb.co", "imageban", "imgbox", "imgur", "img.kiwi", "jpg.church", "jpg.homes", "jpg.fish", "jpg.fishing", "jpg.pet", "jpeg.pet", "jpg1.su", "jpg2.su", "jpg3.su", "kemono", "leakedmodels", "mediafire", "nudostar.com", "nudostar.tv", "omegascans", "pimpandhost", "pixeldrain", "postimg", "reddit", "redd.it", "redgifs", "rule34.xxx", "rule34.xyz", "saint", "scrolller", "simpcity", "socialmediagirls", "toonily", "xbunker", "xbunkr"

***

* only\_hosts

You can supply hosts that you'd like the program to exclusively scrape/download from.

Options:

"bunkrr", "celebforum", "coomer", "cyberdrop", "cyberfile", "e-hentai", "erome", "fapello", "f95zone", "gofile", "hotpic", "ibb.co", "imageban", "imgbox", "imgur", "img.kiwi", "jpg.church", "jpg.homes", "jpg.fish", "jpg.fishing", "jpg.pet", "jpeg.pet", "jpg1.su", "jpg2.su", "jpg3.su", "kemono", "leakedmodels", "mediafire", "nudostar.com", "nudostar.tv", "omegascans", "pimpandhost", "pixeldrain", "postimg", "reddit", "redd.it", "redgifs", "rule34.xxx", "rule34.xyz", "saint", "scrolller", "simpcity", "socialmediagirls", "toonily", "xbunker", "xbunkr"

</details>

<details>

<summary>Runtime Options</summary>

These are higher level options that effect the overarching functions of the program.

***

* ignore\_history

By default the program keeps track of your downloads to make sure you don't download the same things repeatedly (both for you and for the servers you're downloading from)!

Setting this to true will cause the program to ignore the history, and will allow you to re-download files.

***

* skip\_check\_for\_partial\_files

After a run is complete, the program will do a check to see if any partially downloaded files remain in the downloads folder and will notify you of them.

Setting this to true will skip this check.

***

* skip\_check\_for\_empty\_folders

After a run is complete, the program will do a check (and remove) any empty folders in the download folder.

Setting this to true will remove this functionality.

***

* delete\_partial\_files

The program will leave partial files alone as they will be used to resume downloads on subsequent runs.

Setting this to true will remove any partial downloads from the download folder.

***

* send\_unsupported\_to\_jdownloader

By default the program will not send unsupported links to jdownloader.

Setting this to true, will send unsupported links over.

***

* update\_last\_forum\_post

Updates the urls.txt file with the last scraped forum post link for each forum URL.

</details>

<details>

<summary>Sorting</summary>

Cyberdrop-DL has a file sorted built in, but you have to enable it to use it.

You can use the shared path flags below in any part of the sorting schemas. You can also use essentially none of them and have a hard coded path. However, filename and ext must always be used.

Shared Path Flags:

* sort\_dir - sort\_folder path
* base\_dir - the highest level folder name inside the downloads folder
* parent\_dir - the folder name of where the file is
* filename - the files name (stem)
* ext - the files extension

***

* sort\_downloads

Setting this to true will allow Cyberdrop-DL to sort downloads after a run is complete.

***

* sort\_cdl\_only

Setting this to true will sort only files that were downloaded by Cyberdrop-DL. sort_downloads must be true for this to work.

***

* sort\_folder

This is the path to the folder you'd like sorted downloads to be stored in.

***

* sort\_incrementer\_format

When naming collisions happen, Cyberdrop-DL will rename files (image.jpg -> image (1).jpg by default). You can change the way this is formatted. The format simply needs to include a {i}.

***

* sorted\_audio

This is the format for the directory structure and naming scheme for audio files.

Unique Path Flags:

* length - runtime
* bitrate - files bit rate
* sample\_rate - files sample rate

***

* sorted\_image

This is the format for the directory structure and naming scheme for image files.

Unique Path Flags:

* resolution - ex. 1080x1920

***

* sorted\_video

This is the format for the directory structure and naming scheme for video files.

Unique Path Flags:

* resolution - ex. 1080x1920
* fps - ex. 24
* codec - ex. h264

***

* sorted\_other

This is the format for the directory structure and naming scheme for other files.

</details>
