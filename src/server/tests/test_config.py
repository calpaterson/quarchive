from os import environ
from unittest.mock import patch

import pytest

import quarchive as sut


def test_load_config_with_incomplete_config():
    with patch.dict(environ, clear=True):
        with pytest.raises(RuntimeError) as e:
            sut.load_config()
        message = e.value.args[0]
        assert "QM_SQL_URL" in message


def test_load_config_with_test_config():
    with patch.dict(
        environ, {"QM_PASSWORD": "", "QM_SECRET_KEY": "", "QM_SQL_URL": ""}, clear=True
    ):
        sut.load_config()
