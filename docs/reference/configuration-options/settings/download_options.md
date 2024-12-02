# Download Options

## block_download_sub_folders

When this is set to `true`, downloads that would be in a folder structure like:

> `Downloads/folderA/folderB/folderC/image.jpg`

will be changed to:

> `Downloads/folderA/image.jpg`



## disable_download_attempts

By default the program will retry a download 10 times. You can customize this, or set this to `true` (or selected) to disable it and retry links until they complete.

However, to make sure the program will not run endlessly, there are certain situations where a file will never be retried, like if the program receives a 404 HTTP status, meaning the link is dead.



## disable_file_timestamps

By default the program will do it's absolute best to try and find when a file was uploaded. It'll then set the last modified/last accessed/created times on the file to match.

Setting this to `true` (or selecting it) will disable this function, and those times will be the time they were downloaded.



## include_album_id_in_folder_name

Setting this to `true` (or selecting it) will include the album ID (random alphanumeric string) of the album in the download folder name.



## include_thread_id_in_folder_name

Setting this to `true` (or selecting it) will include the thread ID (random alphanumeric string) of the album in the download folder name.



## remove_domains_from_folder_names

Setting this to `true` will remove the "(DOMAIN)" portion of folder names on new downloads.



## remove_generated_id_from_filenames

Setting this to `true` (or selecting it) will remove the alphanumeric ID added to the end of filenames on some websites (ex. Cyberdrop).

Multipart archives filenames will be fixed so they have the proper pattern of their format.

Supported formats: `.rar` `.7z` `.tar` `.gz` `.bz2` `.zip`



## scrape_single_forum_post

Setting this to `true` will result in only a single forum post being scraped on the given link.



## separate_posts

Setting this to `true` (or selecting it) will separate content from forum posts into separate folders.



## skip_download_mark_complete

Setting this to `true` (or selecting it) will skip downloading files and mark them as downloaded in the database.



## skip_referer_seen_before

Setting this to `true` (or selecting it) will skip downloading files from any referer that have been scraped before. The file (s) will always be skipped regardless of whether the referer was successfully scraped or not



## maximum_number_of_children

Limit the number of items to scrape using a tuple of up to 4 positions. Each position defines the maximum number of sub-items (`children_limit`) an specific type of `scrape_item` will have:


1. Max number of children from a **FORUM URL**
2. Max number of children from a **FORUM POST**
3. Max number of children from a **FILE HOST PROFILE**
4. Max number of children from a **FILE HOST ALBUM**


Using `0` on any position means no limit on the number of children for that type of `scrape_item`. Any tailing value not supplied is assumed as `0`

 Examples


Limit FORUM scrape to 15 posts max, grab all links and media within those posts, but only scrape a maximun of 10 items from each link in a post:
```powershell
--maximum-number-of-children 15 0 10

```

Only grab the first link from each post in a forum, but that link will have no children_limit:

```powershell
--maximum-number-of-children 0 1
```


Only grab the first POST/ALBUM from a FILE_HOST_PROFILE
```powershell
--maximum-number-of-children 0 0 1
```


No FORUM limit, no FORUM_POST limit, no FILE_HOST_PROFILE limit, maximum of 20 items from any FILE_HOST_ALBUM:
```powershell
    --maximum-number-of-children 0 0 0 20
```
