import pytest

import quarchive as sut


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("star", "'star'"),
        ("star trek", "'star' & 'trek'"),
        ("'star trek'", "'star' <-> 'trek'"),
        ("'star wars' 'star trek'", "'star' <-> 'wars' | 'star' <-> 'trek'",),
        ("apple 'green red'", "'apple' & 'green' <-> 'red'"),
    ],
)
def test_search_str_parser(session, inp, expected):
    output = sut.parse_search_str(inp)
    assert output == expected

    (rv,) = session.execute("select to_tsquery(:tq_str)", {"tq_str": output}).fetchall()
    assert len(rv) > 0
