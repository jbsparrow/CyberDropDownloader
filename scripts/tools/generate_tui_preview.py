import random
import uuid

from rich.console import Console
from rich.progress import Task, TaskID

from cyberdrop_dl.models.validators import to_bytesize
from cyberdrop_dl.progress.scraping import ScrapingUI
from cyberdrop_dl.progress.scraping.files import FileStats

ui = ScrapingUI()


for link in [
    "https://0101.bandcamp.com/track/mal-damor",
    "https://www.dropbox.com/scl/fo/igg7i2bu3g689",
    "https://mega.nz/folder/yAGGimbjQ#IjoqfoqzesAJIUDq5NKc-Q/folder/zSkgKia",
    *range(321),
]:
    ui.scrape._add_task(link)


ui.files._stats = FileStats(
    completed=7_125,
    prev_completed=1_222,
    skipped=23,
    failed=178,
    queued=458,
)

ui.downloads.get_queue = lambda: ui.files.stats.queued

for error, count in [
    ("410 Gone", 257),
    ("404 Not Found", 53),
    ("Invalid Content Type", 23),
    ("403 Forbidden", 21),
    ("DDoS-Guard", 19),
    ("Password Protected", 16),
    ("Failed Login", 13),
    ("Timeout", 10),
]:
    for _ in range(count):
        ui.scrape_errors.add(error)

for error, count in [
    ("404 Not Found", 125),
    ("502 HTTP Status", 19),
    ("429 Too Many requests", 12),
    ("403 Forbidden", 7),
    ("Client Payload Error", 4),
    ("Client Connector Error", 3),
]:
    for _ in range(count):
        ui.download_errors.add(error)

ui.status._append_msg("Waiting for flaresolverr [2]")

del Task.speed  # pyright: ignore[reportAttributeAccessIssue]
ui.downloads.max_rows = 8
for task_id, (filename, domain, size) in enumerate(
    [
        ("production.bk.db", "MEGA.NZ", to_bytesize("2.5GB")),
        ("Screenrecorder-2022-05-08-20-48-27.mp4", "DROPBOX", to_bytesize("98.2MB")),
        ("FY1tz7EWQAAD3xP.jpg", "DROPBOX", to_bytesize("512.1KB")),
        ("BE13.zip", "PIXELDRAIN", to_bytesize("17MiB")),
        ("World Premiere [avc1][1080p@60fps].mp4", "TWITCH", to_bytesize("3.3MB")),
        ("KILL BILL SAMURAI SWORD REVEAL [fghtyuo]", "PATREON", to_bytesize("146.3MB")),
        ("hotel reception CCTV.mp4", "MEDIAFIRE", 32778299874),
        ("chaku2m-Cf.zip", "FILESTER", to_bytesize("31.2MB")),
        ("75c25022-bb6b-4d45-850c-9966d658ae75.mp4", "BUNKR", to_bytesize("159MB")),
        ("Windward Plains - Hunting Locale [zvbmml]", "PATREON", to_bytesize("1.9GB")),
        *((f"{uuid.uuid4()}.mp4", "BUNKR", int(random.random() * 10e6)) for _ in range(18)),
    ]
):
    hook = ui.downloads.download_file(filename, domain.upper(), size)
    task = ui.downloads._progress[TaskID(task_id)]
    progress = random.random()
    task.speed = min(random.random() * 157e5 + (10e6 * random.random()), progress * size)  # pyright: ignore[reportAttributeAccessIssue]
    hook.advance(int(progress * size))


with Console(record=True, width=150, height=35, color_system="truecolor") as console:
    console.line(3)
    console.print(ui.__rich__())
