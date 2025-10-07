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
            },
            {
                "url": "ANY",
                "filename": "Boeboe - Drift (Bass Boosted).mp4",
                "download_folder": r"re:CDL_test \(GoFile\)/folder_B",
                "referer": "https://gofile.io/d/OP2VyC#229e787c-22e2-4f77-90a5-eb9802788aad",
                "album_id": "OP2VyC",
                "datetime": 1759603323,
            },
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
]
