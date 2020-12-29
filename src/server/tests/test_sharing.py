import flask
from lxml import etree
from lxml.cssselect import CSSSelector

from .conftest import make_bookmark, sign_out
from .utils import sync_bookmarks


def test_access_via_sharelink(signed_in_client, test_user):
    """Check that sharelinks grant access to bookmarks for logged out users
    (and that they can't otherwise see those bookmarks).

    """
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])

    get_form_response = signed_in_client.get(
        flask.url_for(
            "quarchive.share_form",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert get_form_response == 200

    post_form_response = signed_in_client.post(
        flask.url_for(
            "quarchive.create_share",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert post_form_response == 303

    view_url = post_form_response.headers["Location"]
    view_share_response = signed_in_client.get(view_url)
    assert view_share_response.status_code == 200

    # Make sure that the link on the page is as expected
    html_parser = etree.HTMLParser()
    root = etree.fromstring(view_share_response.get_data(), html_parser)
    sharelink_selector = CSSSelector("#share-link")
    sharelink = sharelink_selector(root)[0].text
    expected_base64_share_token = view_url.split("/")[-1]
    assert sharelink == flask.url_for(
        "quarchive.sharelink",
        base64_share_token=expected_base64_share_token,
        _external=True,
    )

    # Now sign out and check we can't access it
    sign_out(signed_in_client)
    expected_view_url = flask.url_for(
        "quarchive.view_bookmark",
        username=test_user.username,
        url_uuid=bm.url.url_uuid,
        _external=True,
    )
    without_share_response = signed_in_client.get(expected_view_url)
    assert without_share_response.status_code == 403

    # Now try following the share link...
    sharelink_response = signed_in_client.get(sharelink)
    assert sharelink_response.status_code == 303
    assert sharelink_response.headers["Location"] == expected_view_url

    # ...and assert that we got access
    with_share_response = signed_in_client.get(expected_view_url)
    assert with_share_response == 200


def test_sharing_with_two_different_links(signed_in_client, test_user):
    """Check that if we share a link multiple times, we get different urls"""
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])

    post_form_response1 = signed_in_client.post(
        flask.url_for(
            "quarchive.create_share",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert post_form_response1 == 303
    view_url1 = post_form_response1.headers["Location"]
    share_token1 = view_url1.split("/")[-1]

    post_form_response2 = signed_in_client.post(
        flask.url_for(
            "quarchive.create_share",
            username=test_user.username,
            url_uuid=bm.url.url_uuid,
        )
    )
    assert post_form_response2 == 303
    view_url2 = post_form_response2.headers["Location"]
    share_token2 = view_url2.split("/")[-1]

    assert share_token1 != share_token2
