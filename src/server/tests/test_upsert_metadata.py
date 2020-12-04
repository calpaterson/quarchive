from quarchive.value_objects import URL
from quarchive.data.models import SQLAUrl
from quarchive.data.functions import upsert_metadata, upsert_url
from quarchive.html_metadata import HTMLMetadata

from .test_indexing import make_crawl_with_response
from .conftest import random_string


def test_upsert_metadata_wholly_new(session, mock_s3):
    """Test upsert_metadata called with a wholly new index"""
    url, crawl_req, _ = make_crawl_with_response(session)
    link_1 = URL.from_string("http://example.com/" + random_string() + "/more")
    link_2 = URL.from_string("http://example.com/" + random_string() + "/even-more")

    metadata = HTMLMetadata(
        url=url.to_url(),
        icons=[],  # FIXME: try a page-level icon
        title="Example page",
        meta_desc="An example page",
        links={link_1, link_2},
    )
    upsert_metadata(session, crawl_req.crawl_uuid, metadata)

    sqla_url_obj = session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url.url_uuid).one()
    link_urls = {o.to_url_obj.to_url() for o in sqla_url_obj.links}
    assert link_urls == {link_1, link_2}
