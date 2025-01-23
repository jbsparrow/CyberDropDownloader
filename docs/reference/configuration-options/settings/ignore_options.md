# Ignore Options

## `exclude_videos`

| Type  | Default |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip downloading video files.

## `exclude_images`

| Type  | Default |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip downloading image files.

## `exclude_audio`

| Type  | Default |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip downloading audio files.

## `exclude_other`

| Type  | Default |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip downloading non media files files.

## `ignore_coomer_ads`

| Type  | Default |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip post marked as ads by models in coomer profiles.

## `skip_hosts`

| Type  | Default |
|----------------|----------|
| `list[NonEmptyStr]` | `[]` |

You can supply hosts that you'd like the program to skip, to not scrape/download from them. This setting accepts any domain, even if they are no supported. When passing hosts as CLI arguments, if the first host is `+`, any hosts after it will be added to the lists of hosts specified in the config file instead of overriding it. Similarly, if the first hosts is `-`, any hosts after it will be removed from the lists of hosts specified in the config

## `only_hosts`

| Type  | Default |
|----------------|----------|
| `list[NonEmptyStr]` | `[]` |

You can supply hosts that you'd like the program to exclusively scrape/download from. This setting accepts any domain, even if they are no supported. When passing hosts as CLI arguments, if the first host is `+`, any hosts after it will be added to the lists of hosts specified in the config file instead of overriding it. Similarly, if the first hosts is `-`, any hosts after it will be removed from the lists of hosts specified in the config

## `filename_regex_filter`

| Type  | Default |
|----------------|----------|
| `NonEmptyStr` or `null` | `null` |

Any download with a filename that matches this regex expression will be skipped
