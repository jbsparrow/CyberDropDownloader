# Sorting

Cyberdrop-DL has a file sorted built in, but you have to enable it to use it.

You can use the shared path flags below in any part of the sorting schemas. You can also use essentially none of them and have a hard coded path. However, `filename` and `ext` must always be used.

Shared path flags:

> `sort_dir`: `sort_folder` path

> `base_dir`: the highest level folder name inside the folder being scanned, ex: (model name / thread name)

> `parent_dir`: the folder name of where the file is (album name)

> `filename`: the files name (stem)

> `ext`: the file extension

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

When naming collisions happen, Cyberdrop-DL will rename files (`image.jpg` -> `image (1).jpg` by default). You can change the way this is formatted. The format simply needs to include `{i}` in it to specify where to put the auto-increment value.

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
