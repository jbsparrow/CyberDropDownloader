DOMAIN = "drive.google"
TEST_CASES = [
    (
        # small file with no warning
        "https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6/edit",
        [
            {
                "url": "ANY",
                "filename": "file-50MB.dat",
                "referer": "https://drive.google.com/file/d/1F0YBsnQRvrMbK0p9UlnyLu88kqQ0j_F6",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # small file with no warning
        "https://drive.google.com/file/d/15WghIO0iwekXStmVWeK5HxC566iN41l6/view",
        [
            {
                "url": "ANY",
                "filename": "file-100MB.dat",
                "referer": "https://drive.google.com/file/d/15WghIO0iwekXStmVWeK5HxC566iN41l6",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # file with warning do to large size (529M)
        "https://drive.usercontent.google.com/download?id=1fXgBupLzThTGLLsiYCHRQJixuDsR1bSI&export=download",
        [
            {
                "url": "ANY",
                "filename": "cifar10_stats.npz",
                "referer": "https://drive.google.com/file/d/1fXgBupLzThTGLLsiYCHRQJixuDsR1bSI",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # Huge file with warning do to large size (9.8G), this test may fail.
        # Public download without an account are limited to about 5G per day and they return 429 with that happens
        "https://drive.google.com/file/d/1WHv5Dm1GtrDZj-AxJZd3T-NMIBXty3eV/view",
        [
            {
                "url": "ANY",
                "filename": "bundle_cutouts_africa.zip",
                "referer": "https://drive.google.com/file/d/1WHv5Dm1GtrDZj-AxJZd3T-NMIBXty3eV",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY/edit",
        [
            {
                "url": "ANY",
                "filename": "test.docx",
                "referer": "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=docx",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=txt",
        [
            {
                "url": "ANY",
                "filename": "test.txt",
                "referer": "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=txt",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=xlsx",
        [
            {
                "url": "ANY",
                "filename": "test.docx",
                "referer": "https://docs.google.com/document/d/1ZzEzJbemBMPm46O2q5VcGNoPbqDu9AhhUc2djQbvbTY?format=docx",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # This is a spreeadsheet but the id is a normal file id
        # We will not be able to download it with a custom format
        "https://docs.google.com/spreadsheets/d/1E3LpudUdUZycJpxSKK-c9-oIDuJoo5_7/edit?format=ods",
        [
            {
                "url": "ANY",
                "filename": "TK Online 1.5.xlsx",
                "referer": "https://drive.google.com/file/d/1E3LpudUdUZycJpxSKK-c9-oIDuJoo5_7",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # v0 file id (28 chars)
        "https://drive.google.com/file/d/0ByeS4oOUV-49Zzh4R1J6R09zazQ/edit",
        [
            {
                "url": "ANY",
                "filename": "Big Buck Bunny.mp4",
                "referer": "https://drive.google.com/file/d/0ByeS4oOUV-49Zzh4R1J6R09zazQ",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        "https://drive.google.com/uc?id=1IP0o8dHcQrIHGgVyp0Ofvx2cGfLzyO1x",
        [
            {
                "url": "ANY",
                "filename": "My Buddy - Henry Burr - Gus Kahn - Walter Donaldson.mp3",
                "referer": "https://drive.google.com/file/d/1IP0o8dHcQrIHGgVyp0Ofvx2cGfLzyO1x",
                "album_id": None,
                "datetime": None,
            }
        ],
    ),
    (
        # Folder with +50 files
        "https://drive.google.com/drive/folders/1k8pgIaGw6PribxVqMgmDtlpzbUPJuzrX",
        [],
        135,
    ),
]
