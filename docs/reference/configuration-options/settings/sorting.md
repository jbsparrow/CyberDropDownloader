# Sorting

Cyberdrop-DL has a file sorted built in, but you have to enable it to use it.

You can use the shared path flags below in any part of the sorting schemas. You can also use essentially none of them and have a hard coded path. However, `filename` and `ext` must always be used.

Shared path flags:

> `sort_dir` - `sort_folder` path

> `base_dir` - the highest level folder name inside the folder being scanned, ex: (model name / thread name)

> `parent_dir` - the folder name of where the file is (album name)

> `filename` - the files name (stem)

> `ext` - the files extension



## Group URLs

It is possible to treat a list of URLs as a group, allowing them to be downloaded to a single folder.

To define a group, put a title above the URLs you want to be in the group by doing the following: `--- <group_name>` or `=== <group_name>`.

To define the end of a group, insert an group with no name. (`---` or `===`)

Here is an example URL file with two groups:

```
https://example.com/file1.jpg
=== Group 1
https://example.com/file2.jpg
https://example.com/file3.jpg
===
https://example.com/file4.jpg
--- Group 2
https://example.com/file5.jpg
https://example.com/file6.jpg
===
https://example.com/file7.jpg
```

Those downloads would be sorted as follows:

| Loose Files | Group 1   | Group 2   |
|-------------|-----------|-----------|
| file1.jpg   | file2.jpg | file5.jpg |
| file4.jpg   | file3.jpg | file6.jpg |
| file7.jpg   |           |           |




## scan_folder

Sets the starting point for the file scan

Each direct child of the `scan_folder` is recursively scanned ,and files are moved based on your settings

If this is set to `null` (the default), `downloads_dir` is used instead



## sort_downloads

Setting this to `true` will allow Cyberdrop-DL to sort downloads after a run is complete.



## sort_cdl_only

Setting this to `true` will sort only files that were downloaded by Cyberdrop-DL. Does nothing if `sort_downloads` is set to `false`



## sort_folder

This is the path to the folder you'd like sorted downloads to be stored in.



## sort_incrementer_format

When naming collisions happen, Cyberdrop-DL will rename files (`image.jpg` -> `image (1).jpg` by default). You can change the way this is formatted. The format simply needs to include `{i}` in it to spscify where to put the auto-increment value.



## sorted_audio

This is the format for the directory structure and naming scheme for audio files.

Unique Path Flags:

> `length` - runtime

> `bitrate` - files bit rate

> `sample_rate` - files sample rate



## sorted_image

This is the format for the directory structure and naming scheme for image files.

Unique Path Flags:

> `resolution` - ex. 1080x1920



## sorted_video

This is the format for the directory structure and naming scheme for video files.

Unique Path Flags:

> `resolution` - ex. 1080x1920

> `fps` - ex. 24

> `codec` - ex. h264



## sorted_other

This is the format for the directory structure and naming scheme for other files.

## Dupe Cleanup Options

These are options for enable/disable hashing and auto dupe delection

To enable auto dupe cleanup:

1. Set `hashing` to `IN_PLACE` or `POST_DOWNLOAD`
2. Set `auto_dedupe` to `true`



## hashing
There are three possible options for hashing

1. `OFF`: disables hashing
2. `IN_PLACE`: performs hashing after each download
3. `POST_DOWNLOAD`: performs hashing after all downloads have completed

The default hasing algorithm is `xxh128`. You can enable aditional hashing algoritms, but you can not replace the default



## auto_dedupe

Enables deduping files functionality. Needs `hashing` to be enabled

This finds all files in the database with the same hash and size, and keeps the oldest copy of the file

Deletion only occurs if two or more matching files are found from the database search



## add_sha256_hash

allows files to be hashed with the `sha256` algorithm, this enables matching with sites that provide this information



## add_md5_hash

allows files to be hash with the `md5` algorithm, this enables matching with sites that provide this information.

{% hint style="info" %}
**md5** was de default hashing algoritm of cyberdrop-dl v5. If you have a database from v5 that you would like to import into v6, is recommend to enable `md5` to match previous hashed files
{% endhint %}



## send_deleted_to_trash

files are sent to trash instead of permanently deleting, enabling easy restoration
