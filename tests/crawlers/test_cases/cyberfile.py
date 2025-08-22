import re

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
                "original_filename": "Sophia Locke  - Inserted (4K).mp4",
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
    (  # File with malformed download URL ( in the slug)
        "https://cyberfile.me/7cfu",
        [
            {
                "url": r"re:https\:\/\/p1\.cyberfile\.me/7cfu/1_Hour_ASMR___\?download_token\=",
                "filename": "1 Hour ASMR.mp4",
                "original_filename": "1 Hour ASMR   ???? ????.mp4",
                "referer": "https://cyberfile.me/7cfu",
                "album_id": None,
                "datetime": 1703854148,
            }
        ],
    ),
    (  # File with emojis in the name
        # This will fail on Windows and MacOS
        "https://cyberfile.me/7cfq",
        [
            {
                "url": "re:"
                + re.escape(
                    "https://p1.cyberfile.me/7cfq/ASMR___1_HOUR_OF_UP-CLOSE_&_PERSONAL_ATTENTION_%E2%9D%A4%EF%B8%8F_NEGATIVE_ENERGY_&_STRESS_REMOVAL_%E2%9D%A4%EF%B8%8F_(LIGHT_LOFI).mp4?download_token="
                ),
                "filename": "ASMR   1 HOUR OF UP-CLOSE & PERSONAL ATTENTION ❤️ NEGATIVE ENERGY & STRESS REMOVAL ❤️ (LIGHT LO.mp4",
                "original_filename": "ASMR   1 HOUR OF UP-CLOSE & PERSONAL ATTENTION ❤️ NEGATIVE ENERGY & STRESS REMOVAL ❤️ (LIGHT LOFI).mp4",
                "referer": "https://cyberfile.me/7cfq",
                "album_id": None,
                "datetime": 1703853101,
            }
        ],
    ),
]
