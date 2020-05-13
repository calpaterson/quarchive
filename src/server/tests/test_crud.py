from uuid import UUID
from datetime import datetime, timezone

from lxml import etree
from lxml.cssselect import CSSSelector
import flask
import pytest
from freezegun import freeze_time

import quarchive as sut

from .conftest import make_bookmark, random_string
from .utils import sync_bookmarks

pytestmark = pytest.mark.web


@pytest.mark.parametrize(
    "inp, exp",
    [
        ({"unread": ""}, {}),
        ({"unread": "on"}, {"unread": "on"}),
        ({"tags": "a,b,c"}, {"tags": ["a", "b", "c"]}),
        ({"tags": "a,b", "add-tag": "c"}, {"tags": ["a", "b", "c"]}),
        ({"tags": "", "add-tag": "a"}, {"tags": ["a"]}),
    ],
)
def test_form_fields_from_querystring(inp, exp):
    assert sut.form_fields_from_querystring(inp) == exp


def test_create_bookmark_form_simple_get(signed_in_client):
    response = signed_in_client.get(flask.url_for("quarchive.create_bookmark_form"))
    assert response.status_code == 200


@pytest.mark.parametrize(
    "viewfunc", ["quarchive.create_bookmark_form", "quarchive.edit_bookmark_form"]
)
@pytest.mark.parametrize(
    "tags_for_param, add_tag, expected_tags",
    [
        (["a", "b"], "c", ["a", "b", "c"]),
        (["a", "b"], "", ["a", "b"]),
        (["a"], "b", ["a", "b"]),
    ],
)
def test_create_bookmark_form_add_tag(
    signed_in_client,
    viewfunc,
    tags_for_param,
    add_tag,
    expected_tags,
    session,
    test_user,
):
    if viewfunc == "quarchive.edit_bookmark_form":
        bookmark = make_bookmark()
        sut.set_bookmark(session, test_user.user_uuid, bookmark)
        url = bookmark.url
    else:
        url = "http://example.com"
    title = "Example"
    description = "A sample website"
    unread = "on"
    tags = ",".join(tags_for_param)
    add_tag = add_tag
    params = {
        "url": url,
        "title": title,
        "description": description,
        "unread": unread,
        "tags": tags,
        "add-tag": add_tag,
    }
    if viewfunc == "quarchive.edit_bookmark_form":
        params["url_uuid"] = sut.create_url_uuid(bookmark.url)
    response = signed_in_client.get(flask.url_for(viewfunc, **params),)

    assert response.status_code == 200
    html_parser = etree.HTMLParser()
    root = etree.fromstring(response.get_data(), html_parser)
    input_elements = CSSSelector("input")(root)
    inputs = {ie.attrib["name"].replace("-input", ""): ie for ie in input_elements}
    description_textarea = CSSSelector("textarea#description-textarea")(root)[0]

    assert inputs["url"].attrib["value"] == url
    assert inputs["title"].attrib["value"] == title
    assert description_textarea.text == description
    assert "checked" in inputs["unread"].attrib
    assert inputs["tags"].attrib["value"] == ",".join(expected_tags)
    assert "value" not in inputs["add-tag"].attrib


@freeze_time("2018-01-03")
def test_edit_bookmark_form_simple_get(signed_in_client, session, test_user):
    bm = make_bookmark()
    sync_bookmarks(signed_in_client, test_user, [bm])

    url_uuid = sut.create_url_uuid(bm.url)

    response = signed_in_client.get(
        flask.url_for("quarchive.edit_bookmark_form", url_uuid=url_uuid)
    )
    assert response.status_code == 200


@freeze_time("2018-01-03")
@pytest.mark.parametrize("unread", [True, False])
@pytest.mark.parametrize("tags", (frozenset([]), frozenset(["a"])))
def test_creating_a_bookmark(test_user, signed_in_client, session, unread, tags):
    url = "http://example.com/" + random_string()
    form_data = dict(
        url=url, title="Example", description="Example description", tags=",".join(tags)
    )
    if unread:
        form_data["unread"] = "on"

    response = signed_in_client.post(
        flask.url_for("quarchive.create_bookmark",), data=form_data
    )
    assert response.status_code == 303

    bookmark = sut.get_bookmark_by_url(session, test_user.user_uuid, url)
    assert bookmark is not None

    assert response.headers["Location"].endswith(
        flask.url_for(
            "quarchive.edit_bookmark_form",
            url_uuid=str(sut.create_url_uuid(bookmark.url)),
        )
    )
    assert bookmark.title == form_data["title"]
    assert bookmark.description == form_data["description"]
    assert bookmark.unread == unread
    assert (
        bookmark.created
        == bookmark.updated
        == datetime(2018, 1, 3, tzinfo=timezone.utc)
    )
    assert bookmark.tags() == tags


jan_1 = datetime(2018, 1, 1, tzinfo=timezone.utc)
mifid2_start_date = datetime(2018, 1, 3, tzinfo=timezone.utc)

tag_params = [
    pytest.param(
        "tag_triples",
        "tags",
        frozenset(),
        "a,b",
        frozenset([("a", mifid2_start_date, False), ("b", mifid2_start_date, False)]),
        id="test adding two tags",
    ),
    pytest.param(
        "tag_triples",
        "tags",
        frozenset([("a", jan_1, False), ("b", jan_1, False)]),
        "a",
        frozenset([("a", jan_1, False), ("b", mifid2_start_date, True)]),
        id="removing a tag",
    ),
]


@freeze_time("2018-01-03")
@pytest.mark.parametrize(
    "obj_attr, form_attr, obj_start, form_value, obj_end",
    [
        ("deleted", "deleted", False, "on", True),
        ("deleted", "deleted", True, None, False),
        ("unread", "unread", False, "on", True),
        ("unread", "unread", True, None, False),
        ("title", "title", "example", "Something else", "Something else"),
        ("description", "description", "example desc", "A desc", "A desc"),
    ]
    + tag_params,
)
def test_editing_a_bookmark(
    signed_in_client,
    session,
    test_user,
    obj_attr,
    form_attr,
    obj_start,
    form_value,
    obj_end,
):
    """Submits the edit bookmark form with varying arguments."""
    bm_args = {obj_attr: obj_start}
    bm = make_bookmark(**bm_args)

    sync_bookmarks(signed_in_client, test_user, [bm])

    url_uuid = sut.create_url_uuid(bm.url)
    form_data = {
        "title": bm.title,
        "description": bm.description,
        "tags": "",
        # "unread": False and "deleted": False are by default
    }
    if form_value is not None:
        form_data[form_attr] = form_value

    response = signed_in_client.post(
        flask.url_for(
            "quarchive.edit_bookmark", url_uuid=url_uuid, redirect_to="/test_location",
        ),
        data=form_data,
    )
    assert response.status_code == 303
    assert response.headers["Location"] == "http://localhost/test_location"

    bookmark_obj = sut.get_bookmark_by_url(session, test_user.user_uuid, bm.url)
    assert getattr(bookmark_obj, obj_attr) == obj_end


def test_editing_a_bookmark_that_doesnt_exist(signed_in_client):
    response = signed_in_client.post(
        flask.url_for(
            "quarchive.edit_bookmark_form",
            url_uuid=UUID("f" * 32),
            redirect_to="/test_location",
        ),
        data={"deleted": "on"},
    )
    assert response.status_code == 404
