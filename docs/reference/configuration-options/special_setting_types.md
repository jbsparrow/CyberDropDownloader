---
description: Configuration settings with special behavior or details.
icon: sparkles
---

# Special Setting Types

## `AdditiveArgs`

Special type for some settings that accept multiple values as input (`lists` or `sets`). When passing values as CLI arguments, if the first value is `+`, any value after it will be added to the values specified in the config file instead of overriding it. Similarly, if the first value is `-`, any value after it will be removed from the values specified in the config

### Examples

If you have the following `skip_hosts` setting in you config file:

```yaml
skip_hosts:
  - drive.google.com
  - youtube.com
  - facebook.com
```

You will get the following results:

| Value you used                                 | Value CDL interpreted                                          | Details                                        |
| ---------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------- |
| `--skip-hosts instagram.com`                    | `[instagram.com]`                                              | config values were overridden by CLI values    |
| `--skip-hosts "+" instagram.com`                | `[drive.google.com, youtube.com, facebook.com, instagram.com]` | config values and CLI values were merged       |
| `--skip-hosts "-" drive.google.com youtube.com` | `[facebook.com]`                                               | CLI values were removed from the config values |

{% hint style="info" %}
Always use quotes for "+" and "-" to make sure your shell does not try to parse them as additional flags
{% endhint %}

## `BoolFlag`

A special kind of `bool`. Within a config file, it can have a `true` or `false` value. However, when used via CLI, the value is assumed from the flag name. The normal name is `true`, and prefixing the name with `--no` means `false`.

### Examples

| Value you used     | Value CDL interpreted |
| ------------------ | --------------------- |
| `--auto-dedupe`    | auto-dedupe: `true`   |
| `--no-auto-dedupe` | auto-dedupe: `false`  |

## `ByteSize`

A special kind of `int` that also accepts suffixes like `GB`, `MiB` and `KB` to specify valid values

In conformance with IEC 80000-13 Standard, `1KB` means `1000 bytes`, and `1KiB` means `1024 bytes`. In general, including a middle 'i' will cause the unit to be interpreted as a power of 2, rather than a power of 10.

### Examples

| Value you used | Value CDL interpreted |
| -------------- | --------------------- |
| `1GB`          | `1.000.000.000 bytes` |
| `512`          | `512 bytes`           |
| `1MiB`         | `1.048.576 bytes`     |

{% hint style="info" %}
`ByteSize` is also used for some settings to specify speed and it's interpreted as `<value> / second`. ex: `8MB` means `8MB/s`
{% endhint %}
