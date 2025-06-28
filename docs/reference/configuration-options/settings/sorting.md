# Sorting

Cyberdrop-DL has a file sorter built in, but it's disabled by default

You can use the field names bellow to create a custom path format. You can also use essentially none of them and have a hard coded path.
However, `filename` and `ext` must always be used.

Common fields for sorting format options (supported for `audio`, `videos`, `images` and `other`):

> `sort_dir`: This represent the same path as `sort_folder` from the download options
>
> `base_dir`: the name of highest level folder inside `scan_folder` ex: (model name / thread name)
>
> `parent_dir`: the name of the folder where the file is located at. Ex: (album name)
>
> `filename`: the file's name (stem)
>
> `ext`: the file extension (suffix)

## `scan_folder`

| Type             | Default |
| ---------------- | ------- |
| `Path` or `null` | `null`  |

Sets the starting point for the file scan

Each direct child of the `scan_folder` is recursively scanned, and files are moved based on your settings.

If this is set to `null` (the default), the value of `download_dir` from  the download options is used.

## `sort_downloads`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will allow Cyberdrop-DL to sort downloads after a run is complete.

## `sort_folder`

| Type   | Default                                   |
| ------ | ----------------------------------------- |
| `Path` | `Downloads/Cyberdrop-DL Sorted Downloads` |

This is the path to the folder you'd like sorted downloads to be stored in.

{% hint style="warning" %}
Setting `sort_folder` to the same value as `scan_folder` is not supported and will lead to expected results
{% endhint %}

## `sort_incrementer_format`

| Type          | Default |
| ------------- | ------- |
| `NonEmptyStr` | `({i})` |

When naming collisions happen, Cyberdrop-DL will rename files automatically

> `image.jpg` -> `image (1).jpg`.

You can modify the format as needed, but it must include `{i}` to specify where the auto-increment value should be placed

## `sorted_audio`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Audio/{filename}{ext}` |

This is the format for the directory structure and naming scheme for audio files. Set to `null` to skip sorting audio files

In addition to the common sorting format fields, this option supports:

> `bitrate`: file bit rate
>
> `duration`: audio total runtime
>
> `length`: same as `duration`
>
> `sample_rate`: audio sample rate

## `sorted_image`

| Type                    | Default                                        |
| ----------------------- | ---------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Images/{filename}{ext}` |

This is the format for the directory structure and naming scheme for image files. Set to `null` to skip sorting image files

In addition to the common sorting format fields, this option supports:

> `height`: vertical pixel count
>
> `width`: horizontal pixel count
>
> `resolution`: `width`x`height` ex. 1080x1920

## `sorted_video`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Video/{filename}{ext}` |

This is the format for the directory structure and naming scheme for video files. Set to `null` to skip sorting video files

In addition to the common sorting format fields, this option supports:

> `codec`: ex. h264
>
> `duration`: video total runtime
>
> `fps`: ex. 24
>
> `length`: same as `duration`
>
> `height`: vertical pixel count
>
> `width`: horizontal pixel count
>
> `resolution`: `width`x`height` ex. 1080x1920

## `sorted_other`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Other/{filename}{ext}` |

This is the format for the directory structure and naming scheme for other files. Set to `null` to skip sorting other files

## Group URLs

It is possible to treat a list of URLs as a group, allowing them to be downloaded to a single folder.

To define a group, put a title above the URLs you want to be in the group, using the format: `--- <group_name>` or `=== <group_name>`.

To define the end of a group, add a new group with no name. (`---` or `===`)

Here is an example URL file with two groups:

```text
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
| ----------- | --------- | --------- |
| file1.jpg   | file2.jpg | file5.jpg |
| file4.jpg   | file3.jpg | file6.jpg |
| file7.jpg   |           |           |
