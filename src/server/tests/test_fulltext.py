from os import path

from quarchive import extract_full_text

from .conftest import test_data_path

import pytest


@pytest.mark.xfail()
def test_get_text_from_html():
    with open(path.join(test_data_path, "test.html"), "rb") as html_f:
        full_text = extract_full_text(html_f)

    assert len(full_text) > 0
