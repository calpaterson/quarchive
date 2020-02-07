import pytest

import quarchive as sut


@pytest.mark.parametrize("inp, expected",[
    ('star', "'star'"),
    ('star trek', "'star' | 'trek'"),
])
def test_search_str_parser(session, inp, expected):
    assert sut.parse_search_str(inp) == expected
