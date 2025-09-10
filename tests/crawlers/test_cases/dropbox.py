DOMAIN = "dropbox"
TEST_CASES = [
    (
        # folder with a single file inside
        "https://www.dropbox.com/scl/fo/6rtuuvcnhe8e0oivnfqtx/AO-LDPRIE_wqGhz8ZyLPWY0?rlkey=zbjcf274goirtfak2prmizi5p&dl=0",
        [
            {
                "url": "https://www.dropbox.com/scl/fo/6rtuuvcnhe8e0oivnfqtx/AAk0xkSvKleGaorbZfRJglA/Spherical-Cow-0.1.1.apk?rlkey=zbjcf274goirtfak2prmizi5p&dl=0",
                "debrid_url": "https://www.dropbox.com/scl/fo/6rtuuvcnhe8e0oivnfqtx/AAk0xkSvKleGaorbZfRJglA/Spherical-Cow-0.1.1.apk?rlkey=zbjcf274goirtfak2prmizi5p&dl=1",
                "filename": "Spherical-Cow-0.1.1.apk",
                "referer": "https://www.dropbox.com/scl/fo/6rtuuvcnhe8e0oivnfqtx/AAk0xkSvKleGaorbZfRJglA/Spherical-Cow-0.1.1.apk?rlkey=zbjcf274goirtfak2prmizi5p&dl=0",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    ("https://www.dropbox.com/scl/fo/igg7i2bazu3g689tqf0i2/h?rlkey=kwqk2vzmiebn9esfgxsm25kaz&dl=0", [], 15),
    (
        # folder with subfolder
        "https://www.dropbox.com/scl/fo/vdsh28mtrlz2dhgazoi6z/AFej9CAhhoEQJo4YDhlbZ0I?dl=0&rlkey=0887klgp6506j3jdy54dnwa6c",
        [
            {
                "url": "https://www.dropbox.com/scl/fo/vdsh28mtrlz2dhgazoi6z/ABWWQ94O950G1irCAniLZDw/Disk_1/sku.sis?rlkey=0887klgp6506j3jdy54dnwa6c&dl=0",
                "filename": "sku.sis",
                "download_folder": r"re:Hacknet Save backup \(Dropbox\)/Disk_1",
            },
            {
                "url": "https://www.dropbox.com/scl/fo/vdsh28mtrlz2dhgazoi6z/AJzG-YDVqQ5VGpGiWsainEM/Disk_1/365454_depotcache_1.csm?rlkey=0887klgp6506j3jdy54dnwa6c&dl=0",
                "filename": "365454_depotcache_1.csm",
                "download_folder": r"re:Hacknet Save backup \(Dropbox\)/Disk_1",
            },
        ],
    ),
    (
        # zipfile. It has a folder URL but is a single file
        "https://www.dropbox.com/scl/fo/vyuocyiqz1j93d71bdz18/ALdJdvzyF0lkH94c8dhztuw/afrojack_presskit_2014.zip?rlkey=hx60uhd3u1cecajczl1x9zn1l&e=1&dl=0",
        [
            {
                "url": "https://www.dropbox.com/scl/fo/vyuocyiqz1j93d71bdz18/ALdJdvzyF0lkH94c8dhztuw/afrojack_presskit_2014.zip?rlkey=hx60uhd3u1cecajczl1x9zn1l&dl=0",
                "debrid_url": "https://www.dropbox.com/scl/fo/vyuocyiqz1j93d71bdz18/ALdJdvzyF0lkH94c8dhztuw/afrojack_presskit_2014.zip?rlkey=hx60uhd3u1cecajczl1x9zn1l&dl=1",
                "filename": "afrojack_presskit_2014.zip",
                "referer": "https://www.dropbox.com/scl/fo/vyuocyiqz1j93d71bdz18/ALdJdvzyF0lkH94c8dhztuw/afrojack_presskit_2014.zip?rlkey=hx60uhd3u1cecajczl1x9zn1l&dl=0",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
]
