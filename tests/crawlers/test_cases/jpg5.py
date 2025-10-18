DOMAIN = "jpg5.su"
TEST_CASES = [
    (
        "https://jpg6.su/img/960x1280-90c58bc6682426b5ff88266b8ec5a647.N3gCSXD",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/960x1280_90c58bc6682426b5ff88266b8ec5a647142c31c72206f9a3.jpg",
                "filename": "960x1280_90c58bc6682426b5ff88266b8ec5a647142c31c72206f9a3.jpg",
                "referer": "https://jpg6.su/img/N3gCSXD",
                "album_id": None,
                "datetime": 1753538118,
            }
        ],
    ),
    (
        "https://jpg6.su/img/2520x3360-ab219efe5d20f99740d58188edd20c440659035b8a5c979d.N3iJfxa",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/2520x3360_ab219efe5d20f99740d58188edd20c440659035b8a5c979d2f40a0e086780c7d.jpg",
                "filename": "2520x3360_ab219efe5d20f99740d58188edd20c440659035b8a5c979d2f40a0e086780c7d.jpg",
                "referer": "https://jpg6.su/img/N3iJfxa",
                "datetime": 1753502011,
            }
        ],
    ),
    (
        "https://jpg6.su/a/testalbum.YnfD4p",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/landscape-mountains-nature-5564166880341c46b7abbe.jpg",
                "filename": "landscape-mountains-nature-5564166880341c46b7abbe.jpg",
                "referer": "https://jpg6.su/img/N3TGEr1",
                "datetime": None,
                "album_id": "YnfD4p",
            },
            {
                "url": "https://simp6.selti-delivery.ru/images3/47749882ae05d0349d87f2d.jpg",
                "filename": "47749882ae05d0349d87f2d.jpg",
                "referer": "https://jpg6.su/img/N3TGCdA",
                "datetime": None,
                "album_id": "YnfD4p",
            },
        ],
    ),
    (
        "https://simp6.jpg5.su/images3/Screenshot-46d10ff096ae50f993.th.png",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/Screenshot-46d10ff096ae50f993.png",
                "filename": "Screenshot-46d10ff096ae50f993.png",
                "referer": "https://simp6.jpg5.su/images3/Screenshot-46d10ff096ae50f993.th.png",
            },
        ],
    ),
    (
        "https://simp6.selti-delivery.ru/images3/rebeca-yellow-pic00910102ed45e07d539.md.jpg",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/rebeca-yellow-pic00910102ed45e07d539.jpg",
                "filename": "rebeca-yellow-pic00910102ed45e07d539.jpg",
                "referer": "https://simp6.selti-delivery.ru/images3/rebeca-yellow-pic00910102ed45e07d539.md.jpg",
            },
        ],
    ),
    (
        "https://jpg6.su/a/rebeca-linares-bikiniriot.aYKmSi/sub",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/rebeca-pink-pic001f1e0e301dd4d56fb.jpg",
                "filename": "rebeca-pink-pic001f1e0e301dd4d56fb.jpg",
                "referer": "https://jpg6.su/img/Nv7ZaLE",
                "datetime": None,
                "download_folder": r"re:Rebeca Linares BikiniRiot \(JPG5\)",
                "album_id": "aYK0fu",
            },
        ],
        285,
    ),
    (
        # Password protected, no password supplied
        "https://jpg6.su/a/alyrosez.Y2Pmn",
        [],
    ),
    (
        # Password protected, incorrect password supplied
        "https://jpg6.su/a/alyrosez.Y2Pmn?password=1234",
        [],
    ),
    (
        # Password protected, valid password supplied
        "https://jpg6.su/a/alyrosez.Y2Pmn?password=aly",
        [
            {
                "url": "https://simp2.selti-delivery.ru/0afcc905cd6c64e52.jpg",
                "filename": "0afcc905cd6c64e52.jpg",
                "referer": "https://jpg6.su/img/ahfHow",
                "datetime": None,
                "download_folder": r"re:alyrosez \(JPG5\)",
                "album_id": "Y2Pmn",
            },
        ],
        1065,
    ),
    (
        "https://jpg5.su/img/NK9wL8h",
        [
            {
                "url": "https://simp6.selti-delivery.ru/images3/Palm-Desert-Resuscitation-Education-YourCPRMD.com4fc75181ec3d573e.png",
                "filename": "Palm-Desert-Resuscitation-Education-YourCPRMD.com4fc75181ec3d573e.png",
                "referer": "https://jpg6.su/img/NK9wL8h",
            },
        ],
    ),
]
