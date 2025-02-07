# Duration Limits

You can provide the maximum and minimum duration for audio and video files.

| Type              | Default  |
|-------------------|----------|
| `timedelta` | `0s`|

- A `timedelta` input is expected to be a valid ISO 8601 timespan, ex: `P10DT2H30M10S`
- An `int` input is assumed to be the number of days
- A  `str` input is expected to be in the format; `<value> <unit>`, ex: `10 days`.

Setting any of these options to `0` means that limit is `disabled`

- `minimum_audio_duration`
- `maximum_audio_duration`
- `minimum_video_duration`
- `maximum_video_duration`
