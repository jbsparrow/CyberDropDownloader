# Ignore Options

## `exclude_videos`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

When this is set to `true` (or selected) the program will skip downloading video files.

## `exclude_images`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

When this is set to `true` (or selected) the program will skip downloading image files.

## `exclude_audio`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

When this is set to `true` (or selected) the program will skip downloading audio files.

## `exclude_other`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

When this is set to `true` (or selected) the program will skip downloading other files.

## `ignore_coomer_ads`

| Type           | Default  |
|----------------|----------|
| `bool` | `false` |

When this is set to `true`, the program will skip past ads posted by models in coomer profiles.

## `skip_hosts`

| Type           | Default  |
|----------------|----------|
| `list[NonEmptyStr]` | `[]` |

You can supply hosts that you'd like the program to skip past, and not scrape/download from. This setting accepts any domain, even if they are no supported

## `only_hosts`

| Type           | Default  |
|----------------|----------|
| `list[NonEmptyStr]` | `[]` |

You can supply hosts that you'd like the program to exclusively scrape/download from. This setting accepts any domain, even if they are no supported
