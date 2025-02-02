---
description: These are the options for controlling the UI of the program
---
# UI Options

## `downloading_item_limit`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `5`     |

This is the limit on the number of items shown in the UI (while downloading) before they are simply added to the overflow number (`and <X> other files`)

## `refresh_rate`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `10`    |

This is the refresh rate per second for the UI.

## `scraping_item_limit`

| Type          | Default |
| ------------- | ------- |
| `PositiveInt` | `5`     |

This is the limit on the number of items shown in the UI (while scraping) before they are simply added to the overflow number (`and <X> other links`)

## `vi_mode`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

This enables vi/vim key binds while editing/entering text in CDL.
