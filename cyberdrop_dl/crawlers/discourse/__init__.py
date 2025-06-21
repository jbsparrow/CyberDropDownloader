# All Discourse websites function exactly the same
# We can create subclasses dynamically by their URL


from cyberdrop_dl.crawlers.crawler import create_crawlers

from ._discourse import DiscourseCrawler

_DISCOURSES_SITES = ["https://forums.plex.tv"]


DISCOURSE_CRAWLERS: set[type[DiscourseCrawler]] = create_crawlers(_DISCOURSES_SITES, DiscourseCrawler)
