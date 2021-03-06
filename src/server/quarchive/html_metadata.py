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

from quarchive.value_objects import URL, URLException, IconScope

log = getLogger(__name__)

Buffer = Union[BinaryIO, gzip.GzipFile]


class Heading(Enum):
    h1 = 1
    h2 = 2
    h3 = 3
    h4 = 4
    h5 = 5
    h6 = 6


@dataclass(frozen=True)
class Icon:
    """Represents a page "icon", like a favicon"""

    url: URL
    scope: IconScope
    rel_text: str
    sizes: Optional[str] = None
    type: Optional[str] = None

    def size_rank(self):
        sizes_regex = re.compile(r"(?P<dim>\d+)x(?P=dim)")
        sizes = self.sizes
        if sizes is None:
            # no idea how big it is, assume tiny
            return 1
        elif sizes == "any":
            # PIL doesn't support vectors, so ignore them
            return -1
        else:
            match = sizes_regex.match(sizes)
            if match is not None:
                return int(match.groups()[0])
            else:
                # junk size, assume tiny
                return -1

    def mimetype(self) -> Optional[str]:
        mimetype: Optional[str]
        if self.type is not None:
            mimetype = self.type
        else:
            mimetype, _ = mimetypes.guess_type(self.url.to_string())
        return mimetype

    def mimetype_rank(self):
        mimetype = self.mimetype()
        ranks: Mapping = {
            "image/png": 2,
            "image/svg+xml": 1,
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
    # We don't currently consider SVG as we can't read them (yet)
    possible_icons = list(
        sorted(
            (i for i in metadata.icons if i.mimetype() != "image/svg+xml"),
            key=lambda i: (i.size_rank(), i.mimetype_rank()),
            reverse=True,
        )
    )
    if len(possible_icons) > 0:
        best_icon = possible_icons[0]
        if best_icon.size_rank() > 0:
            # If the size is wonky, skip it
            log.debug("picked %s as icon for %s", best_icon, metadata.url)
            return best_icon
    url = metadata.url
    fallback_icon = Icon(
        url=URL.from_string(f"{url.scheme}://{url.netloc}/favicon.ico"),
        rel_text="shortcut icon",
        scope=IconScope.DOMAIN,
    )

    log.debug("no icons found on %s, falling back favicon.ico", metadata.url)
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
    rel_canonicals = root.xpath("//head/link[@rel='canonical']")
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
    log.debug("no canonical link found for %s", url)
    return None


def extract_title(root) -> Optional[str]:
    titles = root.xpath("//head/title")
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
    icon_elements = root.xpath(
        "//head/link[(@rel='icon' or @rel='shortcut icon' or @rel='apple-touch-icon' or @rel='alternate icon')]"
    )
    icons = []
    for icon_element in icon_elements:
        icons.append(
            Icon(
                url=url.follow(
                    icon_element.attrib.get("href"), coerce_canonicalisation=True
                ),
                scope=IconScope.PAGE,
                type=icon_element.attrib.get("type"),
                rel_text=icon_element.attrib["rel"],
                sizes=icon_element.attrib.get("sizes"),
            )
        )
    return icons


def extract_first_meta_description(root) -> Optional[str]:
    meta_description_elements = root.xpath("//head/meta[@name='description']")
    if len(meta_description_elements) == 0:
        return None
    else:
        # Multiple meta descriptions are rare(ish) and not supported
        return meta_description_elements[0].attrib.get("content", "")
