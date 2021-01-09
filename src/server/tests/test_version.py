import re

from quarchive.version import get_version


def test_version():
    """Test that we can get the version and that it matches the expected
    pattern.

    """
    # Pip does not allow leading zeros
    assert re.match(r"^[1-9]\d{3}\.[1-9]\d?\.[1-9]\d*$", get_version())
