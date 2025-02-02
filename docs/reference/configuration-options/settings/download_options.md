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

By default the program will retry a download 10 times. You can set this to `true` to disable it and always retry until the download completes.

However, to make sure the program will not run endlessly, there are certain situations where a file will never be retried, like if the program receives a `404` HTTP status, meaning the link is dead.

## `disable_file_timestamps`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

By default the program will do it's absolute best to try and find when a file was uploaded. It'll then set the `last modified`, `last accessed` and `created` dates on the file to match.

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

Limit the number of items to scrape using a tuple of up to 4 positions. Each position defines the maximum number of sub-items (`children_limit`) an specific type of `scrape_item` will have:

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

Setting this to `true` will remove the alphanumeric ID added to the end of filenames by some websites like  `cyberdrop.me`.

Multipart archive filenames will be corrected to follow the proper naming pattern for their format.

Supported formats: `.rar` `.7z` `.tar` `.gz` `.bz2` `.zip`

## `scrape_single_forum_post`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will prevent Cyberdrop-DL to scrape entire thread if an individual post link was provided as input.

## `separate_posts`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Setting this to `true` will separate content from forum and site posts into separate folders. Only affects sites which have 'posts': `Forums`, `reddit`, `coomer`, `kemono` and `nekohouse`.

## `separate_posts_format`

| Type          | Default     |
| ------------- | ----------- |
| `NonEmptyStr` | `{default}` |

This is the format for the directory created when using `--separate-posts`.

Unique Path Flags:

> `date`: date of the post
>
> `number`: post number
>
> `id`: same as `number`
>
> `title`: post title

{% hint style="warning" %}
Not all sites support all possible flags. Ex: Posts from reddit only support the `title` flag
{% endhint %}

Setting it to `{default}` will use the default format, which is different for each crawler:

| Site                              | Default Format     |
| --------------------------------- | ------------------ |
| `Coomer`, `Kemono` an `Nekohouse` | `{date} - {title}` |
| `Forums`                          | `post-{number}`    |
| `Reddit`                          | `{title}`          |

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

| Type           | Default  |
|----------------|----------|
| `NonNegativeInt` | 0 |

{% hint style="warning" %}
It is not recommended to set this above the default value of 0, as there is a high chance of infinite nesting in certain cases.

For example, when dealing with Megathreads, if a Megathread is linked to another Megathread, you could end up scraping an undesirable amount of data.
{% endhint %}

Restricts how many levels deep the scraper is allowed to go while scraping a thread

Values
0: No nesting allowed, only the top level thread is allowed
None: unlimited parents
1>: limits to the value given

### Example
Consider CDL finds the following sub-threads while scraping an input URL:
\```
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
\```
- With `maximum_thread_depth` = 0, CDL will only download files in `thread_01`, all the other threads will be ignored
- With `maximum_thread_depth` = 1, CDL will only download files in `thread_01` to `thread_08`. `thread_09` to `thread_12` will be ignored
- With `maximum_thread_depth` >= 2, CDL will download files from all the threads in this case
