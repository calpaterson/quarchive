import pytest

import quarchive as sut


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("star", "'star'"),
        ("star trek", "'star' | 'trek'"),
        ("'star trek'", "'star' <-> 'trek'"),
        # FIXME: need to do proper parsing to solve this problem
        pytest.param(
            "'star wars' 'star trek'",
            "'star' <-> 'wars' | 'star' <-> 'trek'",
            marks=pytest.mark.xfail,
        ),
    ],
)
def test_search_str_parser(session, inp, expected):
    assert sut.parse_search_str(inp) == expected
