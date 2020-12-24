import json
from uuid import uuid4
from functools import reduce
import operator

import pytz
import pytest

from quarchive.value_objects import User
from quarchive.accesscontrol import (
    Access,
    AccessSubject,
    BookmarkAccessObject,
    from_access_token,
    get_access,
    to_access_token,
)


@pytest.mark.parametrize(
    "inputs, expected",
    [
        ([Access.NONE], Access.NONE),
        ([Access.NONE, Access.READ], Access.READ),
        ([Access.READ, Access.READ], Access.READ),
        ([Access.READ, Access.WRITE], Access.READWRITE),
    ],
)
def test_access_combinations(inputs, expected):
    reduce(operator.and_, inputs, Access.NONE) == expected


owner = User(user_uuid=uuid4(), username="testuser", email=None, timezone=pytz.UTC)
other = User(user_uuid=uuid4(), username="otheruser", email=None, timezone=pytz.UTC)
test_subject = BookmarkAccessObject(user_uuid=owner.user_uuid, url_uuid=uuid4())
test_token = to_access_token(test_subject, Access.READ)
irrelevant_token = to_access_token(
    BookmarkAccessObject(user_uuid=uuid4(), url_uuid=uuid4()), Access.READWRITE
)


def test_access_tokens():
    user_uuid = uuid4()
    url_uuid = uuid4()
    subj = BookmarkAccessObject(user_uuid=user_uuid, url_uuid=url_uuid)
    token = to_access_token(subj, Access.READ)
    assert json.loads(token) == {
        "n": "bookmark",
        "q": {"user_uuid": user_uuid.hex, "url_uuid": url_uuid.hex},
        "a": 1,
    }

    assert from_access_token(token) == (subj, Access.READ)
    assert len(token) == 121


@pytest.mark.parametrize(
    "subject,user,access_tokens,expected",
    [
        pytest.param(test_subject, owner, [], Access.READWRITE, id="ownership"),
        pytest.param(test_subject, other, [], Access.NONE, id="other"),
        pytest.param(
            test_subject, None, [test_token], Access.READ, id="access-token-based"
        ),
        pytest.param(
            test_subject, None, [irrelevant_token], Access.NONE, id="no relevant token"
        ),
        pytest.param(
            test_subject,
            None,
            [irrelevant_token, test_token],
            Access.READ,
            id="two tokens token",
        ),
    ],
)
def test_get_access(subject, user, access_tokens, expected):
    assert get_access(AccessSubject(user, access_tokens), subject) == expected
