DOMAIN = "mediafire"
TEST_CASES = [
    (
        "https://www.mediafire.com/file/ctppmpm7giofsgv/ADOFAI.vpk/file",
        [
            {
                "url": "re:https://download",
                "filename": "ADOFAI.vpk",
                "referer": "https://www.mediafire.com/file/ctppmpm7giofsgv",
                "album_id": None,
                "datetime": 1695838138,
            }
        ],
    ),
    (
        "https://www.mediafire.com/?511jd1358yxvf26",
        [
            {
                "url": "re:https://download",
                "filename": "ipwn1x-1.0.iso",
                "referer": "https://www.mediafire.com/file/511jd1358yxvf26",
                "album_id": None,
                "datetime": 1654132657,
            }
        ],
    ),
    (
        "https://www.mediafire.com/folder/ixh40veo6hrc5/kcc_samples",
        [
            {
                "url": "re:https://download",
                "filename": "kobo_clara.kepub.epub",
                "referer": "https://www.mediafire.com/file/5iv342h2u39e0t6",
                "download_folder": r"re:kcc samples \(Mediafire\)",
                "album_id": "ixh40veo6hrc5",
                "datetime": 1746643902,
            },
        ],
        11,
    ),
    (
        "https://www.mediafire.com/folder/m3sij67rizpb4/XJTU-SY_Bearing_Datasets",
        [
            {
                "url": "re:https://download",
                "filename": "XJTU-SY_Bearing_Datasets.part02.rar",
                "referer": "https://www.mediafire.com/file/sqbsl8ja9c9e84x",
                "download_folder": r"re:XJTU-SY_Bearing_Datasets \(Mediafire\)/Data",
                "album_id": "0m0g59yk1pmh5",
            },
            {
                "url": "re:https://download",
                "filename": "ReadMe.txt",
                "referer": "https://www.mediafire.com/file/4tu93kyda5jp6qh",
                "download_folder": r"re:XJTU-SY_Bearing_Datasets \(Mediafire\)",
                "album_id": "m3sij67rizpb4",
            },
            {
                "url": "re:https://download",
                "filename": "Download_Links_20190306.txt",
                "referer": "https://www.mediafire.com/file/8ovwh5726b44e9f",
                "download_folder": r"re:XJTU-SY_Bearing_Datasets \(Mediafire\)",
                "album_id": "m3sij67rizpb4",
            },
        ],
        18,
    ),
    (
        "https://www.mediafire.com/folder/9a6a91cgbd7m8",
        [],
        36,
    ),
    (
        "https://www.mediafire.com/folder/ujs6wzw0cecof/",  # DMCA folder
        [],
    ),
]
