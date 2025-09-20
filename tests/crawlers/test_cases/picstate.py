DOMAIN = "picstate.com"
TEST_CASES = [
    (
        "https://picstate.com/view/full/5391859_e3p1g",
        [
            {
                "url": "https://picstate.com/files/5391859_e3p1g/Naked_Diva__2005_.jpg",
                "filename": "Naked_Diva__2005_.jpg",
                "referer": "https://picstate.com/view/full/5391859_e3p1g",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://picstate.com/files/5391859_e3p1g/Naked_Diva__2005_.jpg",
        [
            {
                "url": "https://picstate.com/files/5391859_e3p1g/Naked_Diva__2005_.jpg",
                "filename": "Naked_Diva__2005_.jpg",
                "referer": "https://picstate.com/view/full/5391859_e3p1g",
            }
        ],
    ),
    (
        "https://picstate.com/thumbs/small/5391859_e3p1g/Naked_Diva__2005_.jpg",
        [
            {
                "url": "https://picstate.com/files/5391859_e3p1g/Naked_Diva__2005_.jpg",
                "filename": "Naked_Diva__2005_.jpg",
                "referer": "https://picstate.com/view/full/5391859_e3p1g",
            }
        ],
    ),
]
