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

| Type                | Default  | Additional Info |
|---------------------|----------| --------------- |
| `list[NonEmptyStr]` | `[]`     | This is an [`AdditiveArg`](../special_setting_types.md#AdditiveArgs)

You can supply hosts that you'd like the program to skip, to not scrape/download from them. This setting accepts any domain, even if they are no supported.

## `only_hosts`

| Type                | Default  | Additional Info |
|---------------------|----------| --------------- |
| `list[NonEmptyStr]` | `[]`     | This is an [`AdditiveArg`](../special_setting_types.md#AdditiveArgs)

You can supply hosts that you'd like the program to exclusively scrape/download from. This setting accepts any domain, even if they are no supported.

{% hint style="info" %}
This setting is an `Additive`
{% endhint %}

## `filename_regex_filter`

| Type  | Default |
|----------------|----------|
| `NonEmptyStr` or `null` | `null` |

Any download with a filename that matches this regex expression will be skipped
