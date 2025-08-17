DOMAIN = "cyberfile"
TEST_CASES = [
    (
        "https://cyberfile.me/c5w9",
        [
            {
                "url": r"re:https\:\/\/p2\.cyberfile\.me/c5w9/ANGEL_MOVIE_082\.mp4\?download_token\=",
                "filename": "ANGEL_MOVIE_082.mp4",
                "referer": "https://cyberfile.me/c5w9",
                "album_id": None,
                "datetime": 1726579084,
            }
        ],
    ),
    (
        "https://cyberfile.me/shared/-dprdwxcs8",
        [
            {
                "url": r"re:https\:\/\/p2\.cyberfile\.me/88pe/WAAA-127\.mp4\?download_token\=",
                "filename": "WAAA-127.mp4",
                "referer": "https://cyberfile.me/88pe",
                "download_folder": r"re:JAV \(Cyberfile\)",
                "album_id": "-dprdwxcs8",
                "datetime": 1728519855,
            }
        ],
    ),
    (
        "https://cyberfile.me/b8lt",
        [
            {
                "url": r"re:https\:\/\/p1\.cyberfile\.me/b8lt/Sophia_Locke__-_Inserted_\(4K\).mp4\?download_token\=",
                "filename": "Sophia Locke  - Inserted (4K).mp4",
                "original_filename": "Sophia_Locke__-_Inserted_(4K).mp4",
                "referer": "https://cyberfile.me/b8lt",
                "album_id": None,
                "datetime": 1696232232,
            }
        ],
    ),
    (
        "https://cyberfile.me/shared/avk-q2uqnz",
        [
            {
                "url": r"re:https\:\/\/p1\.cyberfile\.me/71nn/tabooheat\.23\.03\.29\.cory\.chase\.and\.sophia\.locke\.4k\.mp4\?download_token\=",
                "filename": "tabooheat.23.03.29.cory.chase.and.sophia.locke.4k.mp4",
                "referer": "https://cyberfile.me/71nn",
                "download_folder": r"re:Sophia Locke \(Cyberfile\)",
                "album_id": "avk-q2uqnz",
                "datetime": 1698316590,
            }
        ],
        44,
    ),
    (
        # Password protected folder, no password supplied
        "https://cyberfile.me/folder/30cab170dd652309c8b8f25aaba4ec85/Autumn_Falls_JulesJordan_Videos",
        [],
    ),
    (
        # Password protected folder, invalid password supplied
        "https://cyberfile.me/folder/30cab170dd652309c8b8f25aaba4ec85/Autumn_Falls_JulesJordan_Videos?password=1234",
        [],
    ),
    (
        # Password protected folder, valid password supplied
        "https://cyberfile.me/folder/30cab170dd652309c8b8f25aaba4ec85/Autumn_Falls_JulesJordan_Videos?password=studio",
        [
            {
                "url": r"re:https\:\/\/p1\.cyberfile\.me/8QdR/www\.0xxx\.ws_JulesJordan\.20\.03\.03\.Autumn\.Falls\.XXX\.1080p\.MP4-KTR\.mp4\?download_token\=",
                "filename": "www.0xxx.ws_JulesJordan.20.03.03.Autumn.Falls.XXX.1080p.MP4-KTR.mp4",
                "referer": "https://cyberfile.me/8QdR",
                "download_folder": r"re:Autumn Falls JulesJordan Videos \(Cyberfile\)",
                "album_id": "30cab170dd652309c8b8f25aaba4ec85",
                "datetime": 1669199683,
            }
        ],
        6,
    ),
    (
        # Password protected file
        "https://cyberfile.me/ktP2",
        [],
    ),
    (
        # Password protected file
        "https://cyberfile.me/ktP2?password=pass",
        [
            {
                "url": r"re:https\:\/\/p2\.cyberfile\.me/ktP2/HIPANGEL_021\.mp4\?download_token\=",
                "filename": "HIPANGEL_021.mp4",
                "referer": "https://cyberfile.me/ktP2",
                "album_id": None,
                "datetime": 1726582638,
            }
        ],
    ),
]
