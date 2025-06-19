# All Discourse websites function exactly the same
# We can create subclasses dynamically by their URL


from cyberdrop_dl.crawlers.crawler import _create_subclass

from ._discourse import DiscourseCrawler

_DISCOURSES_SITES = ["https://forums.plex.tv"]


DISCOURSE_CRAWLERS: set[type[DiscourseCrawler]] = {_create_subclass(url, DiscourseCrawler) for url in _DISCOURSES_SITES}
