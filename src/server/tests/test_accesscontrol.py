from uuid import uuid4
from functools import reduce
import operator
from datetime import datetime

import pytz
import pytest

from quarchive.value_objects import User
from quarchive.accesscontrol import (
    Access,
    AccessSubject,
    BookmarkAccessObject,
    ShareGrant,
    get_access,
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


def test_share_params():
    user_uuid = uuid4()
    url_uuid = uuid4()
    subj = BookmarkAccessObject(user_uuid=user_uuid, url_uuid=url_uuid)
    assert subj.to_params() == {
        "user_uuid": user_uuid.hex,
        "url_uuid": url_uuid.hex,
    }
    assert BookmarkAccessObject.from_params(subj.to_params()) == subj


owner = User(
    user_uuid=uuid4(),
    username="testuser",
    email=None,
    timezone=pytz.UTC,
    registered=datetime.utcnow(),
)
other = User(
    user_uuid=uuid4(),
    username="otheruser",
    email=None,
    timezone=pytz.UTC,
    registered=datetime.utcnow(),
)
test_subject = BookmarkAccessObject(user_uuid=owner.user_uuid, url_uuid=uuid4())
test_grant = ShareGrant(
    share_token=b"",
    expiry=None,
    access_object=test_subject,
    access_verb=Access.READ,
    revoked=False,
)
irrelevant_grant = ShareGrant(
    share_token=b"",
    expiry=None,
    access_object=BookmarkAccessObject(user_uuid=uuid4(), url_uuid=uuid4()),
    access_verb=Access.READWRITE,
    revoked=False,
)


@pytest.mark.parametrize(
    "subject,user,grants,expected",
    [
        pytest.param(test_subject, owner, [], Access.ALL, id="ownership"),
        pytest.param(test_subject, other, [], Access.NONE, id="other"),
        pytest.param(
            test_subject, None, [test_grant], Access.READ, id="access-token-based"
        ),
        pytest.param(
            test_subject, None, [irrelevant_grant], Access.NONE, id="no relevant token"
        ),
        pytest.param(
            test_subject,
            None,
            [irrelevant_grant, test_grant],
            Access.READ,
            id="two tokens token",
        ),
    ],
)
def test_get_access(subject, user, grants, expected):
    assert get_access(AccessSubject(user, grants), subject) == expected
