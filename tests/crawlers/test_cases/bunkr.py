DOMAIN = "bunkrr"
TEST_CASES = [
    (
        # No datetime info
        "https://bunkr.pk/f/k3B4hDIRexYfV",
        [
            {
                "url": "re:Stepmom.+Best.Friend.mp4",
                "filename": "Katalina Kyle, Savanah Storm - What If She Hears Us! Caught Fucking My Stepmoms Best Friend.mp4",
                "original_filename": "4260d330-9881-4324-8bf4-87657e5c11c5.mp4",
                "referer": "https://bunkr.site/f/k3B4hDIRexYfV",
                "datetime": None,
            }
        ],
    ),
    (
        # paginated
        "https://bunkr.cr/a/5aZU25Cb",
        [
            {
                "url": "https://mlk-bk.cdn.gigachad-cdn.ru/01101506-9a96-4379-a226-c27f128923f6.jpg?n=xl_g_elin_maddie150.jpg",
                "filename": "xl_g_elin_maddie150.jpg",
                "original_filename": "01101506-9a96-4379-a226-c27f128923f6.jpg",
                "referer": "https://bunkr.site/f/1EhT44cSv6Dlq",
                "download_folder": r"re:abbywinters - Elin & Maddie \(Girl - Girl Extra Large\)",
                "album_id": "5aZU25Cb",
                "datetime": 1755391253,
            }
        ],
        258,
    ),
    (
        "https://bunkr.cr/a/TQAgjP8m",
        [
            {
                "url": "re:2020-01-09---Fake-Porn-Star-Orders-Pizza-NAKED-Prank----6dh068JH.mp4",
                "filename": "2020-01-09 - Fake Porn Star Orders Pizza NAKED Prank 🍕.mp4",
                "original_filename": "2020-01-09---Fake-Porn-Star-Orders-Pizza-NAKED-Prank----6dh068JH.mp4",
                "referer": "https://bunkr.site/f/UAvbs2GPhWOGc",
                "download_folder": r"re:NerdballerTV - Videos \(2018-2023\) \[Complete\]",
                "album_id": "TQAgjP8m",
                "datetime": 1709776012,
            }
        ],
        220,
    ),
    (
        # .org domain redirect to a different domain and discards query params
        # This test is to make sure CDL does not get stuck in an infinite loop while doing album pagination
        "https://bunkrrr.org/a/n12rHpzB",
        [],
        142,
    ),
    (
        "https://bunkr.ax/v/rFicV4QnhSHBE",
        [
            {
                "url": r"re:1df93418-5063-4e1b-851e-9470cb8fc5c6\.mp4",
                "filename": "MysteriousProd.24.09.06.April.Olsen.Rebel.Rhyder.All.About.Fucking.720p.mp4",
                "original_filename": "1df93418-5063-4e1b-851e-9470cb8fc5c6.mp4",
                "referer": "https://get.bunkrr.su/file/41348624",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
]
