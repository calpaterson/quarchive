import re

from quarchive.version import get_version


def test_version():
    """Test that we can get the version and that it matches the expected
    pattern.

    """
    assert re.match(r"^\d{4}.\d{2}.\d$", get_version())
