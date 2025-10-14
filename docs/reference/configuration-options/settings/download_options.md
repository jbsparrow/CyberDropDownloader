# Download Options

## `block_download_sub_folders`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

When this is set to `true`, downloads that would be in a folder structure like:

> `Downloads/folderA/folderB/folderC/image.jpg`

will be changed to:

> `Downloads/folderA/image.jpg`

## `disable_download_attempts`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

By default the program will retry a download twice. You can set this to `true` to disable it and always retry until the download completes.

However, to make sure the program will not run endlessly, there are certain situations where a file will never be retried, like if the program receives a `404` HTTP status, meaning the link is dead.

## `disable_file_timestamps`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

By default the program will do it's absolute best to try and find the upload date of a file. It'll then set the `last modified` and `last accessed` dates on the file to match. On Windows and macOS, it will also try to set the `created` date.

Setting this to `true` will disable this function, and the dates for those metadata entries will be the date the file was downloaded.

## `include_album_id_in_folder_name`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will include the album ID (random alphanumeric string) of the album in the download folder name.

## `include_thread_id_in_folder_name`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will include the thread ID (random alphanumeric string) of the forum thread in the download folder name.

## `maximum_number_of_children`

| Type                   | Default |
| ---------------------- | ------- |
| `list[NonNegativeInt]` | `[]`    |

Limit the number of items to scrape using a tuple of up to 4 positions. Each position defines the maximum number of sub-items (`children_limit`) a specific type of `scrape_item` will have:

1. Max number of children from a **FORUM URL**
2. Max number of children from a **FORUM POST**
3. Max number of children from a **FILE HOST PROFILE**
4. Max number of children from a **FILE HOST ALBUM**

Using `0` on any position means no limit on the number of children for that type of `scrape_item`. Any tailing value not supplied is assumed as `0`

### Examples

{% tabs %}
{% tab title="example 1" %}
Limit **FORUM** scrape to 15 posts max, grab all links and media within those posts, but only scrape a maximum of 10 items from each link in a post:

```shell
--maximum-number-of-children 15 0 10

```

{% endtab %}

{% tab title="example 2" %}
Only grab the first link from each post in a forum, but that link will have no `children_limit`:

```shell
--maximum-number-of-children 0 1
```

{% endtab %}

{% tab title="example 3" %}
Only grab the first **POST** / **ALBUM** from a **FILE_HOST_PROFILE**

```shell
--maximum-number-of-children 0 0 1
```

{% endtab %}

{% tab title="example 4" %}
No **FORUM** limit, no **FORUM_POST** limit, no **FILE_HOST_PROFILE** limit, maximum of 20 items from any **FILE_HOST_ALBUM**:

```shell
    --maximum-number-of-children 0 0 0 20
```

{% endtab %}
{% endtabs %}

## `remove_domains_from_folder_names`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will remove the "(DOMAIN)" portion of folder names on new downloads.

## `remove_generated_id_from_filenames`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will remove the alphanumeric ID added to the end of filenames by some websites.

This option only works for URLs from `cyberdrop.me` at the moment.

Multipart archive filenames will be corrected to follow the proper naming pattern for their format.

Supported formats: `.rar` `.7z` `.tar` `.gz` `.bz2` `.zip`

## `scrape_single_forum_post`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will prevent Cyberdrop-DL from scraping an entire thread if the input URL had an specific post in it.

CDL will only download files within that post.

For most forum sites, the post id is part of the fragment in the URL.

ex: `/thread/iphone-16-16e-16-plus-16-pro-16-promax.256047/page-64#post-7512404` has a post id of `7512404`

If `scrape_single_forum_post` is `false`, CDL will download all post in the thread, from post `7512404` until the last post

If `scrape_single_forum_post` is `true`, CDL will only download files within post `7512404` itself and stop.

## `separate_posts`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will separate content from forum and site posts into separate folders.

This option only works with sites that have 'posts':

- `Forums`
- `Discourse`
- `reddit`
- `Tiktok`
- `Coomer`, `Kemono` and `Nekohouse`.

For some sites, this value is hardcorded to `true` because each post is always an individual page:

- `Wordpress`
- `eFukt`

## `separate_posts_format`

| Type          | Default     |
| ------------- | ----------- |
| `NonEmptyStr` | `{default}` |

This is the format for the directory created when using `--separate-posts`.

Unique Path Flags:

> `date`: date of the post. This is a python `datetime` object
>
> `id`: The post id. This is always a `string`, even if some sites use numbers
>
> `number`: This no longer means anything. Currently, it always has the same value as `id`
>
> `title`: post title. This is a `string`

{% hint style="warning" %}
Not all sites support all possible flags. Ex: Posts from reddit only support the `title` flag

If you use a format with a field that the site does not support, CDL will replace it with `UNKNOWN_<FIELD_NAME>`

ex: using the format `reddit post #{id}` will result in `reddit post #UNKNOWN_ID`
{% endhint %}

Setting it to `{default}` will use the default format, which is different for each crawler:

| Site                                  | Default Format                     |
| ------------------------------------- | ---------------------------------- |
| `Coomer`, `Kemono` and `Nekohouse`    | `{date} - {title}`                 |
| `Forums (Xenforo/vBulletin/Invision)` | `{date} - {id} - {title}`          |
| `Discourse`                           | `{date} - {id} - {title}`          |
| `Reddit`                              | `{title}`                          |
| `WordPress`                           | `{date:%Y-%m-%d} - {id} - {title}` |
| `eFukt`                               | `{date:%Y-%m-%d} {title}`          |
| `Tiktok`                              | `{date:%Y-%m-%d} - {id}`          |

A date without a `format_spec` defaults to ISO 8601 format

You can use any valid format string supported by python, with the following restrictions:

- You can not have positional arguments in the format string. ex: `post {0} from date {1}`
- You can not have unnamed fields in the format string. ex:  `post {} from date {}`
- You can not perform operations within the format string. ex:  `post {id + 1} from date {date}`
- All the fields named in the format string must be valid fields for that format option. CDL will validate this at startup

## `skip_download_mark_completed`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will skip the download process for every file and mark them as downloaded in the database.

## `skip_referer_seen_before`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will skip downloading files from any referer that have been scraped before. The file (s) will always be skipped, regardless of whether the referer was successfully scraped or not

## `maximum_thread_depth`

| Type             | Default |
| ---------------- | ------- |
| `NonNegativeInt` | 0       |

{% hint style="warning" %}
It is not recommended to set this above the default value of `0`, as there is a high chance of infinite nesting in certain cases.

For example, when dealing with Megathreads, if a Megathread is linked to another Megathread, you could end up scraping an undesirable amount of data.
{% endhint %}

Restricts how many levels deep the scraper is allowed to go while scraping a thread

A value of `0` means only the top level thread will be scraped

{% hint style="info" %}
This setting is hardcoded to `0` for Discourse sites
{% endhint %}

### Example

Consider CDL finds the following sub-threads while scraping an input URL:

```shell
└── thread_01
    ├── thread_02
    ├── thread_03
    │   ├── thread_09
    │   ├── thread_10
    │   └── thread_11
    ├── thread_04
    ├── thread_05
    ├── thread_06
    ├── thread_07
    │   └── thread_12
    └── thread_08
```

- With `maximum_thread_depth` = 0, CDL will only download files in `thread_01`, all the other threads will be ignored
- With `maximum_thread_depth` = 1, CDL will only download files in `thread_01` to `thread_08`. All threads from `thread_09` to `thread_12` will be ignored
- With `maximum_thread_depth` >= 2, CDL will download files from all the threads in this case

## `maximum_thread_folder_depth`

| Type                       | Default |
| -------------------------- | ------- |
| `NonNegativeInt` or `None` | `None`  |

Restricts the max number of nested folders CDL will create when `maximum_thread_depth` is greater that 0

Values:

- `None`: Create as many nested folders as required (AKA, the same number as  `maximum_thread_depth` allows)
- `0`: Do not create subfolders, use a flat structure for any nested thread.
- `1+`: Create a max of `n` folders

### Example

- With `maximum_thread_folder_depth` = None:

```shell
└── thread_01
    ├── thread_02
    ├── thread_03
    │   ├── thread_09
    │   ├── thread_10
    │   └── thread_11
    ├── thread_04
    ├── thread_05
    ├── thread_06
    ├── thread_07
    │   └── thread_12
    └── thread_08
```

- With `maximum_thread_folder_depth` = 0:

```shell
├── thread_01
├── thread_02
├── thread_03
├── thread_09
├── thread_10
├── thread_11
├── thread_04
├── thread_05
├── thread_06
├── thread_07
├── thread_12
└── thread_08
```

- With `maximum_thread_folder_depth` = 1:

```shell
└── thread_01
    ├── thread_02
    ├── thread_03
    ├── thread_09
    ├── thread_10
    ├── thread_11
    ├── thread_04
    ├── thread_05
    ├── thread_06
    ├── thread_07
    ├── thread_12
    └── thread_08
```
