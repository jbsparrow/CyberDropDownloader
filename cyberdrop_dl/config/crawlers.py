from typing import Annotated, Any, Literal, override

from pydantic import Field
from pydantic.functional_validators import AfterValidator, field_validator

from cyberdrop_dl.models import ConfigGroup, ConfigModel
from cyberdrop_dl.models.types import FormatStr, HttpURL, NonEmptyStr
from cyberdrop_dl.models.validators import remove_duplicates, strings


class GoogleDriveFormats(ConfigModel):
    docs: Literal["docx", "odt", "rtf", "txt", "epub", "pdf", "md", "zip"] = "docx"
    "Default format for documents (can be overridden per URL with the 'format' query param)"

    sheets: Literal["xslx", "ods", "html", "csv", "tsv"] = "xslx"
    "Default format for spreedsheets (can be overridden per URL with the 'format' query param)"

    slides: Literal["pptx", "odp"] = "pptx"
    "Default format for presentations (can be overridden per URL with the 'format' query param)"

    @field_validator("*", mode="before")
    @classmethod
    def _remove_dots(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lstrip(".")
        return value


class GoogleDriveConfig(ConfigModel):
    default_formats: GoogleDriveFormats = Field(default_factory=GoogleDriveFormats)


class KemonoConfig(ConfigModel):
    file: bool = True
    "Download the main file in a post (if any)"

    attachments: bool = True
    "Download all attachments in a post (may or may not include `file`)"

    content_urls: bool = True
    "Download any URL found inside the description (text) of a post (slower)"

    embed: bool = True
    "Download the embedded file from third party sites (if any)(mega.nz, pcloud, dropbox, etc..)"


class TikTokConfig(ConfigModel):
    original: bool = False
    "Download videos in original quality (slower)"


class TwitterArticlesConfig(ConfigModel):
    cover: bool = True
    "Download the cover image of articles"

    media: bool = True
    "Download media files in the body of articles"


class TwitterConfig(ConfigModel):
    cards: bool = True
    "Parse and download cards in a post (embeds from thirdparty sites)"

    threads: bool = True
    "Downloads all posts in a thread (All direct replies from OP to their own tweet)"

    content_urls: bool = True
    "Parse and try to download any URL found inside the text of a tweet"

    articles: TwitterArticlesConfig = Field(default_factory=TwitterArticlesConfig)
    # Articles are longer tweets for premium users

    retweets: bool = False
    "Download media from retweets in the user's timeline"

    image_size: Literal["orig", "4096x4096", "large", "medium", "small", "thumb"] = "orig"
    # `orig`` is original quality but it's not always available, same as "4096x4096"
    # "large", "medium", or "small" are always available


class OctaveMusicConfig(ConfigModel):
    quality: Literal["lossless", "mp3-320"] = "mp3-320"
    "Quality of audio file to download (lossless are .flac files)"

    filename_format: Annotated[
        FormatStr,
        strings.format_validator(
            {
                "artist",
                "artists",
                "writer",
                "writers",
                "composer",
                "composers",
                "release_date",
                "title",
                "ext",
                "track_number",
                "disk_number",
            }
        ),
    ] = "{artist} - {title}{ext}"
    "Format to generate audio file"


class BandcampConfig(ConfigModel):
    formats: Annotated[
        tuple[Literal["mp3-320", "mp3", "aac-hi", "wav", "flac", "vorbis", "aiff", "alas"], ...],
        AfterValidator(remove_duplicates),
    ] = (
        "mp3-320",
        "mp3",
        "aac-hi",
        "wav",
        "flac",
        "vorbis",
        "aiff",
        "alas",
    )
    "Format to choose for downloads (if available), ordered by preference"


class ClypitConfig(ConfigModel):
    prefer_mp3: bool = False
    """Download audios as .mp3 files even if WAV (high quality) versions are available"""


class OnePaceConfig(ConfigModel):
    prefer_dub: bool = False
    """Download episodes with english audio tracks instead of japanese (if available)"""


class ClonrConfig(ConfigModel):
    use_source: bool = False
    "Ignore files in clone and process the original Mega.nz URL"

    zip: bool = False
    "Download entire clone as a single ZIP file"

    @override
    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        if self.use_source and self.zip:
            raise ValueError("'clonr.zip' and 'clonr.use_source' are mutually exclusive")


class PornHubConfig(ConfigModel):
    profile_paths: tuple[NonEmptyStr, ...] = "photos/public", "gifs/public", "videos", "videos/upload"
    "Subpaths to scrape when an input URL is a profile's homepage"

    @override
    def model_post_init(self, context: Any, /) -> None:
        super().model_post_init(context)
        self.profile_paths = tuple(p.lstrip("/") for p in self.profile_paths)


class GenericCrawlers(ConfigModel):
    wordpress_media: tuple[HttpURL, ...] = ()
    wordpress_html: tuple[HttpURL, ...] = ()
    discourse: tuple[HttpURL, ...] = ()
    chevereto: tuple[HttpURL, ...] = ()
    kvs: tuple[HttpURL, ...] = ()
    video: tuple[HttpURL, ...] = ()
    peertube: tuple[HttpURL, ...] = ()


class Crawlers(ConfigGroup, name=None):
    disabled: set[NonEmptyStr] = Field(default_factory=set)
    "Name of crawlers to disable for the current run"

    bandcamp: BandcampConfig = Field(default_factory=BandcampConfig)
    clonr: ClonrConfig = Field(default_factory=ClonrConfig)
    clypit: ClypitConfig = Field(default_factory=ClypitConfig)
    generic: GenericCrawlers = Field(default_factory=GenericCrawlers)
    google_drive: GoogleDriveConfig = Field(default_factory=GoogleDriveConfig)
    octave_music: OctaveMusicConfig = Field(default_factory=OctaveMusicConfig)
    one_pace: OnePaceConfig = Field(default_factory=OnePaceConfig)
    only_haven: KemonoConfig = Field(default_factory=KemonoConfig)
    pawchive: KemonoConfig = Field(default_factory=KemonoConfig)
    pornhub: PornHubConfig = Field(default_factory=PornHubConfig)
    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
