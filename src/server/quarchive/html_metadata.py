from typing import Sequence, Optional, BinaryIO, Union, Mapping, Tuple
import gzip
from dataclasses import dataclass, field
from enum import Enum

import lxml
import lxml.html

from quarchive.value_objects import URL

Buffer = Union[BinaryIO, gzip.GzipFile]


class Header(Enum):
    h1 = 1
    h2 = 2
    h3 = 3
    h4 = 4
    h5 = 5
    h6 = 6


@dataclass
class HTMLMetadata:
    favicons: Sequence[Tuple[URL, Mapping[str, str]]] = field(default_factory=list)
    canonical: Optional[URL] = None
    title: Optional[str] = None
    headings: Mapping[Header, Sequence[str]] = field(default_factory=dict)
    meta_desc: Optional[str] = None
    links: Sequence[URL] = field(default_factory=list)
    text: Optional[str] = None

    def best_favicon(self) -> URL:
        ...


def extract_metadata_from_html(filelike: Buffer) -> HTMLMetadata:
    """Parse the HTML, extracting the metadata."""
    metadata = HTMLMetadata()
    document = lxml.html.parse(filelike)
    root = document.getroot()
    metadata.text = extract_full_text(root)
    metadata.meta_desc = extract_first_meta_description(root)
    return metadata


def extract_full_text(root) -> str:
    # FIXME: This is very basic but will do for now
    return root.text_content()


def extract_first_meta_description(root) -> Optional[str]:
    meta_description_elements = root.xpath("//meta[@name='description']")
    if len(meta_description_elements) == 0:
        return None
    else:
        # Multiple meta descriptions are rare(ish) and not supported
        return meta_description_elements[0].attrib.get("content", "")
