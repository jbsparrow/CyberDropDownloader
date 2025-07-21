---
description: These are the options to define generic crawlers.

---

CDL has some "generic" crawlers disabled by default. Generic crawlers are designed to work on any site that uses a **specific** framework. Users can supply a list of sites to map to these crawlers, and CDL will then be able to download from them. The URL in the list should be the primary URL of the site. ex: `https://forums.docker.com/`

Currently, there are three generic crawlers:

- `chevereto`: This works on any site that uses [Chevereto](https://chevereto.com//).

- `discourse`: This works on any forum that uses [Discourse](https://www.discourse.org/).

- `wordpress_html`: This works on any WordPress site. It scrapes the actual HTML of the site, which means it works even on sites that have embedded third-party media like videos or links to hosting sites. It is always slower than `wordpress_media`.

- `wordpress_media`: This crawler should work on any [WordPress](https://wordpress.com/) site where content primarily consists of images or galleries. The images need to be hosted on the site itself. It requires sites to have a public WordPress REST API.

# generic_crawlers_instances

## `chevereto`

| Type            | Default |
| --------------- | ------- |
| `list[HttpURL]` | `[]`    |

## `discourse`

| Type            | Default |
| --------------- | ------- |
| `list[HttpURL]` | `[]`    |

## `wordpress_html`

| Type            | Default |
| --------------- | ------- |
| `list[HttpURL]` | `[]`    |

## `wordpress_media`

| Type            | Default |
| --------------- | ------- |
| `list[HttpURL]` | `[]`    |
