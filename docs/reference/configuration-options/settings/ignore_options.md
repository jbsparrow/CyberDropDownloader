# Ignore Options

## `exclude_audio`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, the program will skip downloading audio files.

## `exclude_images`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, the program will skip downloading image files.

## `exclude_videos`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, the program will skip downloading video files.

## `exclude_other`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, the program will skip downloading non media files files.

## `exclude_files_with_no_extension`

| Type                | Default  |
|---------------------|----------|
| `bool`              | `true`   |

When this is set to `true`, the program will skip downloading files without an extension.

{% hint style="info" %}
CDL internally assumes any file without an extension is an `.mp4` file. That means any option that applies to videos like `--exclude-videos` and `--minimum-video-size` will apply to them. The actual file will still be downloaded without an extension
{% endhint %}

## `filename_regex_filter`

| Type                    | Default |
| ----------------------- | ------- |
| `NonEmptyStr` or `null` | `null`  |

Any download with a filename that matches this regex expression will be skipped

## `ignore_coomer_ads`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, the program will skip post marked as ads by models in coomer profiles.

## `only_hosts`

| Type                | Default | Additional Info                                                     |
| ------------------- | ------- | ------------------------------------------------------------------- |
| `list[NonEmptyStr]` | `[]`    | This is an [`AdditiveArg`](../special_setting_types.md#additiveargs) |

You can supply hosts that you'd like the program to exclusively scrape/download from. This setting accepts any domain, even if they are no supported.

## `skip_hosts`

| Type                | Default | Additional Info                                                      |
| ------------------- | ------- | -------------------------------------------------------------------- |
| `list[NonEmptyStr]` | `[]`    | This is an [`AdditiveArg`](../special_setting_types.md#additiveargs) |

You can supply hosts that you'd like the program to skip, to not scrape/download from them. This setting accepts any domain, even if they are no supported.
