# Sorting

Cyberdrop-DL has a file sorter built in, but you have to enable it to use it.

You can use the shared path flags below in any part of the sorting schemas. You can also use essentially none of them and have a hard coded path. However, `filename` and `ext` must always be used.

Shared path flags:

> `sort_dir`: `sort_folder` path
> `base_dir`: the highest level folder name inside the folder being scanned, ex: (model name / thread name)
> `parent_dir`: the folder name of where the file is (album name)
> `filename`: the files name (stem)
> `ext`: the file extension

## Group URLs

It is possible to treat a list of URLs as a group, allowing them to be downloaded to a single folder.

To define a group, put a title above the URLs you want to be in the group, using the format: `--- <group_name>` or `=== <group_name>`.

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


## `scan_folder`

| Type           | Default  |
|----------------|----------|
| `Path` or `null` | `null`|

Sets the starting point for the file scan

Each direct child of the `scan_folder` is recursively scanned, and files are moved based on your settings

If this is set to `null` (the default), `download_dir` is used instead

## `sort_downloads`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Setting this to `true` will allow Cyberdrop-DL to sort downloads after a run is complete.

## `sort_cdl_only`

| Type           | Default  |
|----------------|----------|
| `bool` | `false`|

Setting this to `true` will sort only files that were downloaded by Cyberdrop-DL. Does nothing if `sort_downloads` is set to `false`

## `sort_folder`

| Type           | Default  |
|----------------|----------|
| `Path` | `Downloads/Cyberdrop-DL Sorted Downloads`|

This is the path to the folder you'd like sorted downloads to be stored in.


{% hint style="warning" %}
Setting `sort_folder` to the same value as `scan_folder` is not officiality supported and will lead to undefined results
{% endhint %}

## `sort_incrementer_format`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | ` ({i})`|

When naming collisions happen, Cyberdrop-DL will rename files automatically
> `image.jpg` -> `image (1).jpg`.

You can modify the format as needed, but it must include `{i}` to specify where the auto-increment value should be placed

## `sorted_audio`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | `{sort_dir}/{base_dir}/Audio/{filename}{ext}`|

This is the format for the directory structure and naming scheme for audio files.

Unique Path Flags:

> `length`: audio runtime
> `bitrate`: file bit rate
> `sample_rate`: audio sample rate

## `sorted_image`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | `{sort_dir}/{base_dir}/Images/{filename}{ext}`|

This is the format for the directory structure and naming scheme for image files.

Unique Path Flags:

> `resolution`: ex. 1080x1920

## `sorted_video`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | `{sort_dir}/{base_dir}/Video/{filename}{ext}`|

This is the format for the directory structure and naming scheme for video files.

Unique Path Flags:

> `resolution`: ex. 1080x1920
> `fps`: ex. 24
> `codec`: ex. h264

## `sorted_other`

| Type           | Default  |
|----------------|----------|
| `NonEmptyStr` | `{sort_dir}/{base_dir}/Other/{filename}{ext}`|

This is the format for the directory structure and naming scheme for other files.
