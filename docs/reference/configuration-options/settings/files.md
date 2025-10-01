# Files

## `download_folder`

| Type   | Default     |
| ------ | ----------- |
| `Path` | `Downloads` |

The path to the folder you want Cyberdrop-DL to download files to.

## `dump_json`

| Type   | Default |
| ------ | ------- |
| `bool` | `False` |

If enabled, CDL will created a [json lines](https://jsonlines.org/) files with the information about every file downloaded in the current run. The path to this file will be the same as `--main-log` but with the extension `.results.jsonl`

Each line in the file will contain the following details (this may change on future versions):

```json
{
    "url": "https://store9.gofile.io/download/web/7c88c147-ABCD-4e4d-9a6c-12345678/a_video.mp4",
    "referer": "https://gofile.io/d/ABC123",
    "download_folder": "Downloads/Cyberdrop-DL Downloads/test_album (GoFile)",
    "filename": "0hxte0li0o931lwgcrzbz_source.mp4",
    "original_filename": "a_video.mp4",
    "download_filename": "0hxte0li0o931lwgcrzbz_source.mp4",
    "filesize": 12054723,
    "ext": ".mp4",
    "debrid_link": null,
    "duration": null,
    "album_id": "ABC123",
    "datetime": "2025-01-22T11:00:07",
    "parents": ["https://a_forum.com/threads/<name>.54321/post-123123"],
    "parent_threads": ["https://a_forum.com/threads/<name>.54321"],
    "partial_file": "Downloads/Cyberdrop-DL Downloads/test_album (GoFile)/a_video.mp4.part",
    "complete_file": "Downloads/Cyberdrop-DL Downloads/test_album (GoFile)/a_video.mp4",
    "hash": "xxh128:53ee56b7bfafa31b8780a572e9783df3",
    "downloaded": true,
    "attempts": 1

}
```

## `input_file`

| Type   | Default                             |
| ------ | ----------------------------------- |
| `Path` | `AppData/Configs/{config}/URLs.txt` |

The path to the text file containing the URLs you want to download. Each line should be a single URL.

You can also use `html` code. Cyberdrop-DL will parse all the links on the HTML

## `save_pages_html`

| Type   | Default |
| ------ | ------- |
| `bool` | `False` |

CDL will save to disk a copy of every requests as an html file. The files will be saved to a folder named `cdl_responses`, located in the same folder as the main log file.

{% hint style="info" %}
Not every request made by CDL returns an HTML page (ex: API requests generally return JSON data). Only HTML responses will be saved
{% endhint %}
