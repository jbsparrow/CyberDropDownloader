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

Multipart archives filenames will be fixed so they have the proper pattern of their format.

Supported formats: `.rar` `.7z` `.tar` `.gz` `.bz2` `.zip`


***

* scrape\_single\_forum\_post

Setting this to true will result in only a single forum post being scraped on the given link.

***

* separate\_posts

Setting this to true (or selecting it) will separate content from forum posts into separate folders.

***

* skip\_download\_mark\_complete

Setting this to true (or selecting it) will skip downloading files and mark them as downloaded in the database.

***

* skip\_referer\_seen\_before

Setting this to true (or selecting it) will skip downloading files from any referer that have been scraped before. The file (s) will always be skipped regardless of whether the referer was successfully scraped or not

***

* maximum\_number\_of\_children

Limit the number of items to scrape using a tuple of up to 4 positions. Each position defines the maximum number of sub-items (`children_limit`) an specific type of `scrape_item` will have:

    1. Max number of children from a FORUM URL
    2. Max number of children from a FORUM POST
    3. Max number of children from a FILE HOST PROFILE
    4. Max number of children from a FILE HOST ALBUM

Using `0` on any position means no `children_limit` for that type of `scrape_item`. Any tailing value not supplied is assumed as `0`



Examples:

```
Limit FORUM scrape to 15 posts max, grab all links and media within those posts, but only scrape a maximun of 10 items from each link in a post:

    --maximum-number-of-children 15 0 10


Only grab the first link from each post in a forum, but that link will have no children_limit:

    --maximum-number-of-children 0 1


Only grab the first POST/ALBUM from a FILE_HOST_PROFILE

    --maximum-number-of-children 0 0 1


No FORUM limit, no FORUM_POST limit, no FILE_HOST_PROFILE limit, maximum of 20 items from any FILE_HOST_ALBUM:

    --maximum-number-of-children 0 0 0 20
``` 

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

***

* discord\_webhook\_url

The URL of the Discord webhook that you want to send download stats to. You can add the optional tag `attach_logs=` as a prefix to include a copy of the main log as an attachment. 

Ex: `attach_logs=https://discord.com/api/webhooks/webhook_id/webhook_token`

***

* rotate\_logs

If enabled, Cyberdrop-DL will add the current date and time as a suffix to each log file, in the format `YYMMDD_HHMMSS`

This will prevent overriding old log files

Files that will be rotated:

| option                       | default_filename              |
|------------------------------|-------------------------------|
| download_error_urls_filename |  Download_Error_URLs.csv      |
| last_forum_post_filename     |  Last_Scraped_Forum_Posts.csv |
| main_log_filename            |  downloader.log               |
| scrape_error_urls_filename   |  Scrape_Error_URLs.csv        |
| unsupported_urls_filename    |  Unsupported_URLs.csv         |

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

After a run is complete, the program will do a check (and remove) any empty files and folders in the download and scan folder.

Setting this to true will disable this functionality.

***

* delete\_partial\_files

The program will leave partial files alone as they will be used to resume downloads on subsequent runs.

Setting this to true will remove any partial downloads from the download folder.

***

* send\_unsupported\_to\_jdownloader

By default the program will not send unsupported links to jdownloader.

Setting this to `true`, will send unsupported links over.

***

* jdownloader\_autostart

Defaults to `false`. Setting this to `true` will make jdownloader start downloads as soon as they are sent.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

***

* jdownloader\_download_dir:

The `download_dir` jdownloader will use. A `null` value (the default) will make jdownloader use the same `download_dir` as CDL. Use this option as path mapping when jdownloader is running on a diferent host / docker.

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

***

* jdownloader\_whitelist

List of domain names. An unsupported URL will only be sent to jdownloader if its host is found in on the list. An empty whitelist (the default) will disable this funtionality, sending any unsupported URL to jdownloader

This option has no effect unless `send_unsupported_to_jdownloader` is `true`

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
* base\_dir - the highest level folder name inside the folder being scanned 'scan\_folder' (model name / thread name)
* parent\_dir - the folder name of where the file is (album name)
* filename - the files name (stem)
* ext - the files extension

It is possible to treat a list of URLs as a group, allowing them to be downloaded to a single folder.

To define a group, put a title above the URLs you want to be in the group by doing the following: `--- {group name}` or `=== {group name}`.

To define the end of a group, insert an group with no name. (`---` or `===`)

Here is an example URL file with two groups:

```
https://example.com/file1.jpg
=== Test
https://example.com/file2.jpg
https://example.com/file3.jpg
===
https://example.com/file4.jpg
--- Test 2
https://example.com/file5.jpg
https://example.com/file6.jpg
===
https://example.com/file7.jpg
```

Those downloads would be sorted as follows:

<img src="../../.gitbook/assets/Screen Shot 2024-09-23 at 11.09.50.png" alt="" data-size="original">

***

* scan\_folder

Sets the starting point for the file scan

Each direct child of the scan\_folder is recursively scanned ,and files are moved based on your settings

If this is not set then the downloads\_dir is used instead

***

* sort\_downloads

Setting this to true will allow Cyberdrop-DL to sort downloads after a run is complete.

***

* sort\_cdl\_only

Setting this to true will sort only files that were downloaded by Cyberdrop-DL. sort\_downloads must be true for this to work.

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
