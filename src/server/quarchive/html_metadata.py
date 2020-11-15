import re
from typing import Sequence, Optional, BinaryIO, Union, Mapping, Set
import gzip
from dataclasses import dataclass, field
from enum import Enum
import mimetypes
from logging import getLogger
from collections import defaultdict

import lxml
import lxml.html

from quarchive.value_objects import URL, URLException

log = getLogger(__name__)

Buffer = Union[BinaryIO, gzip.GzipFile]


class Heading(Enum):
    h1 = 1
    h2 = 2
    h3 = 3
    h4 = 4
    h5 = 5
    h6 = 6


class IconScope(Enum):
    DOMAIN = "domain"
    PAGE = "page"


@dataclass
class Icon:
    """Represents a page "icon", like a favicon"""

    url: URL
    scope: IconScope
    metadata: Mapping[str, str] = field(default_factory=dict)

    def size_rank(self):
        sizes_regex = re.compile(r"(?P<dim>\d+)x(?P=dim)")
        sizes = self.metadata.get("sizes")
        if sizes is None:
            # no idea how big it is, assume tiny
            return 1
        elif sizes == "any":
            # it's a vector, so return a big number
            return 10_000
        else:
            match = sizes_regex.match(sizes)
            if match is not None:
                return int(match.groups()[0])
            else:
                return -1

    def mimetype_rank(self):
        mimetype: Optional[str]
        if "type" in self.metadata:
            mimetype = self.metadata["type"]
        else:
            mimetype, _ = mimetypes.guess_type(self.url.to_string())
        ranks: Mapping = {
            "image/png": 2,
            "image/svg+xml": 3,
        }
        return ranks.get(mimetype, 0)


@dataclass
class HTMLMetadata:
    url: URL
    icons: Sequence[Icon] = field(default_factory=list)
    canonical: Optional[URL] = None
    title: Optional[str] = None
    headings: Mapping[Heading, Sequence[str]] = field(default_factory=dict)
    meta_desc: Optional[str] = None
    links: Set[URL] = field(default_factory=set)
    text: Optional[str] = None


def best_icon(metadata: HTMLMetadata) -> Icon:
    """Will return the most suitable icon for our purposes, falling back to the
    domain level favicon.ico if nothing else is available."""
    url = metadata.url
    fallback_icon = Icon(
        url=URL.from_string(f"{url.scheme}://{url.netloc}/favicon.ico"),
        scope=IconScope.DOMAIN,
    )

    if len(metadata.icons) > 0:
        best_icon = sorted(
            metadata.icons,
            key=lambda i: (i.size_rank(), i.mimetype_rank()),
            reverse=True,
        )[0]
        if best_icon.size_rank() > 0:
            # If the size is wonky, skip it
            return best_icon

    return fallback_icon


def extract_metadata_from_html(url: URL, filelike: Buffer) -> HTMLMetadata:
    """Parse the HTML, extracting the metadata."""
    metadata = HTMLMetadata(url=url)
    document = lxml.html.parse(filelike)
    root = document.getroot()
    metadata.text = extract_full_text(root)
    metadata.meta_desc = extract_first_meta_description(root)
    metadata.icons = extract_icons(root, url)
    metadata.canonical = extract_canonical_link(root, url)
    metadata.title = extract_title(root)
    metadata.links = extract_links(root, url)
    metadata.headings = extract_headings(root)
    return metadata


def extract_canonical_link(root, url: URL) -> Optional[URL]:
    rel_canonicals = root.xpath("//link[@rel='canonical']")
    if len(rel_canonicals) > 0:
        if "href" in rel_canonicals[0].attrib:
            href = rel_canonicals[0].attrib["href"]
            try:
                return url.follow(href, coerce_canonicalisation=True)
            except URLException:
                log.debug("bad canonical link: %s (from %s)", href, url)
        else:
            log.debug("canonical link with no href on %s", url)
            return None
    return None


def extract_title(root) -> Optional[str]:
    titles = root.xpath("//title")
    if len(titles) > 0:
        return titles[0].text_content()
    return None


def extract_links(root, url: URL) -> Set[URL]:
    rv: Set[URL] = set()
    for anchor in root.xpath("//a"):
        if "href" in anchor.attrib:
            href: str = anchor.attrib["href"]
            try:
                rv.add(url.follow(href, coerce_canonicalisation=True))
            except URLException:
                log.debug("bad link: %s (from: %s)", href, url)
    return rv


def extract_headings(root) -> Mapping[Heading, Sequence[str]]:
    headings_elements = root.xpath("//h1 | //h2 | //h3 | //h4 | //h5 | //h6")
    rv = defaultdict(lambda: [])
    for elem in headings_elements:
        rv[Heading[elem.tag]].append(elem.text_content())
    return rv


def extract_full_text(root) -> str:
    # FIXME: This is very basic but will do for now
    return root.text_content()


def extract_icons(root, url: URL) -> Sequence[Icon]:
    icon_elements = root.xpath("//link[@rel='icon']")
    icons = []
    for icon_element in icon_elements:
        metadata = {}
        if "type" in icon_element.attrib:
            metadata["type"] = icon_element.attrib["type"]
        icons.append(
            Icon(
                url=url.follow(
                    icon_element.attrib.get("href"), coerce_canonicalisation=True
                ),
                scope=IconScope.PAGE,
                metadata=metadata,
            )
        )
    return icons


def extract_first_meta_description(root) -> Optional[str]:
    meta_description_elements = root.xpath("//meta[@name='description']")
    if len(meta_description_elements) == 0:
        return None
    else:
        # Multiple meta descriptions are rare(ish) and not supported
        return meta_description_elements[0].attrib.get("content", "")
