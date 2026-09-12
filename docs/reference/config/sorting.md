`cyberdrop-dl` has a file sorter built in, but it's not enabled by default.

You can use the field names below to create a custom path format. You can also use none of them and have a hard coded path for sorted files.
However, `filename` and `ext` should always be used as files will overwrite each other otherwise.

Common fields for sorting format options (supported for `audio`, `videos`, `images` and `other`):

> `base_dir`: the name of highest level folder inside `scan_folder`. This normally is the model name or the thread name
>
> `ext`: the file extension (suffix)
>
> `file_date`: the file date. This is a datetime object, which means it accepts a custom format spec ex: `{file_date:%Y-%m}`
>
> `file_date_iso`: the file date as an iso 8601 string (`%Y-%m-%d`)
>
> `file_date_us`: the file date in the US format (`%Y-%d-%m`)
>
> `filename`: the file's name (stem)
>
> `parent_dir`: the name of the folder where the file is located at (its parent folder). This is normally the album name for photos or the post name for forums/reddit if `separate_post` is enabled
>
> `sort_dir`: the same path as `sort_folder` from the download options

# `enabled`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Enable/Disabled file sorting at the end of a download session. All other sorting options are ignored if this is `false`

```yaml
sort:
  enabled: false
```

# `input_folder`

| Type             | Default |
| ---------------- | ------- |
| `Path` or `null` | `null`  |

Sort all files within this folder. Subfolders are recursively scanned, and files are moved based on your settings.

A value of `null` (the default) will use the save folder as `--download-folder`.

```yaml
sort:
  input_folder: null
```

# `output_folder`

| Type   | Default                         |
| ------ | ------------------------------- |
| `Path` | `downloads/cyberdrop-dl sorted` |

This is the path to the folder you'd like sorted downloads to be stored in.

{% hint style="warning" %}
Setting `--sort.output_folder` to the same value as `--sort.input_folder` (or a subfolder of it) is not supported and will lead to expected results
{% endhint %}

```yaml
sort:
  output_folder: downloads/cyberdrop-dl sorted
```

# Formats

## `audio`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Audio/{filename}{ext}` |

This is the format for the directory structure and naming scheme for audio files. Set to `null` to skip sorting audio files

In addition to the common sorting format fields, this option supports:

> `bitrate`: file bit rate. This is an `int`
>
> `duration`: audio total runtime in seconds. This is an `int`
>
> `length`: same as `duration`
>
> `sample_rate`: audio sample rate. This is an `int`

```yaml
sort:
  formats:
    audio: "{sort_dir}/{base_dir}/Audio/{filename}{ext}"
```

## `image`

| Type                    | Default                                        |
| ----------------------- | ---------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Images/{filename}{ext}` |

This is the format for the directory structure and naming scheme for image files. Set to `null` to skip sorting image files

In addition to the common sorting format fields, this option supports:

> `height`: vertical pixel count. This is an `int`
>
> `width`: horizontal pixel count. This is an `int`
>
> `resolution`: `width`x`height` ex. 1080x1920. This is a `str`

```yaml
sort:
  formats:
    image: "{sort_dir}/{base_dir}/Images/{filename}{ext}"
```

## `video`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Video/{filename}{ext}` |

This is the format for the directory structure and naming scheme for video files. Set to `null` to skip sorting video files

In addition to the common sorting format fields, this option supports:

> `codec`: ex. h264. This is a `str`. It could potentially be `null` for some files
>
> `duration`: video total runtime in seconds. This is an `int`
>
> `fps`: ex. `24`. This represents a number but is a `str`. It could potentially be `null` for some files
>
> `length`: same as `duration`
>
> `height`: vertical pixel count. This is an `int`
>
> `width`: horizontal pixel count.This is an `int`
>
> `resolution`: `width`x`height` ex. 1080x1920. This is a `str`

```yaml
sort:
  formats:
    video: "{sort_dir}/{base_dir}/Videos/{filename}{ext}"
```

## `non_media`

| Type                    | Default                                       |
| ----------------------- | --------------------------------------------- |
| `NonEmptyStr` or `null` | `{sort_dir}/{base_dir}/Other/{filename}{ext}` |

This is the format for the directory structure and naming scheme for other files. Set to `null` to skip sorting other files

```yaml
sort:
  formats:
    non_media: "{sort_dir}/{base_dir}/Other/{filename}{ext}"
```

## `incrementer`

| Type          | Default  |
| ------------- | -------- |
| `NonEmptyStr` | ` ({i})` |

When naming collisions happen, `cyberdrop-dl` will rename files automatically

> `image.jpg` -> `image (1).jpg`.

You can modify the format as needed, but it must include `{i}` to specify where the auto-increment value should be placed

```yaml
sort:
  formats:
    incrementer: " ({i})"
```

# Comments

Lines that start with `#` are ignored.

A line containing only `#` starts a block comment. Everything up to the next line containing only `#` is ignored, URLs included:

```text
https://example.com/file1.jpg
#
https://example.com/file2.jpg
https://example.com/file3.jpg
#
https://example.com/file4.jpg
```

Only `file1.jpg` and `file4.jpg` would be downloaded.

If a block comment is never closed, every URL after it is ignored and a warning is logged.

Block comments have no effect inside a group. There, a line with only `#` is just an ordinary comment.

# Group URLs

It is possible to treat a list of URLs as a group, allowing them to be downloaded to a single folder.

To define a group, put a title above the URLs you want to be in the group, using the format: `--- <group_name>` or `=== <group_name>`.

To define the end of a group, add a new group with no name. (`---` or `===`)

Here is an example `URLs.txt` file with two groups:

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

And downloaded to the following folders:

```shell
└── downloads
    ├── Group 1
    │   ├── file2.jpg
    │   └── file3.jpg
    ├── Group 2
    │   ├── file5.jpg
    │   └── file6.jpg
    └── Loose Files
        ├── file1.jpg
        ├── file4.jpg
        └── file7.jpg

```
