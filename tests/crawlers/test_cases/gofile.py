DOMAIN = "gofile"
TEST_CASES = [
    (
        "https://gofile.io/d/2ORt9N",
        [
            {
                "url": "re:download/web/f1f28c6a-d02b-44a3-80ec-d9ef6b23913e",
                "filename": "[5ahw24au]chance-01.mp4",
                "original_filename": "[5ahw24au]chance-01.mp4",
                "download_folder": r"re:Loose Files \(GoFile\)",
                "referer": "https://gofile.io/d/2ORt9N#f1f28c6a-d02b-44a3-80ec-d9ef6b23913e",
                "datetime": 1756801442,
            }
        ],
    ),
    (
        "https://gofile.io/d/u9Yhqb",
        [
            {
                "url": "ANY",
                "filename": "Apashe - Majesty (Instrumental).webm",
                "download_folder": r"re:CDL_test \(GoFile\)/folder_A",
                "referer": "https://gofile.io/d/0272Cc#386c2d54-548a-4fd1-abde-6f7c91b25a5d",
                "album_id": "0272Cc",
                "datetime": 1759603311,
            }
        ],
    ),
    ("https://gofile.io/d/tZeyhP?password=wrong_password", []),
    (
        "https://gofile.io/d/tZeyhP?password=cdl_password",
        [
            {
                "url": "ANY",
                "filename": "Apashe - Majesty (Instrumental).webm",
                "download_folder": r"re:CDL_test_password \(GoFile\)/folder_A",
                "referer": "https://gofile.io/d/T3gI1u#26617578-4770-41fb-9352-cad172b10b35",
                "album_id": "T3gI1u",
            },
        ],
    ),
    (
        "https://store6.gofile.io/download/69b4c1e4-a80a-45d5-ad76-061e48105bd0/MORE_IN90.mp4",
        [
            {
                "url": "https://store3.gofile.io/download/web/69b4c1e4-a80a-45d5-ad76-061e48105bd0/MORE_IN90.mp4",
                "filename": "MORE_IN90.mp4",
                "download_folder": r"re:01 \(GoFile\)",
                "referer": "https://gofile.io/d/9d83784e-2be6-472c-909f-0377704cfde3#69b4c1e4-a80a-45d5-ad76-061e48105bd0",
                "album_id": "9d83784e-2be6-472c-909f-0377704cfde3",
                "datetime": 1701541586,
            },
        ],
    ),
]
