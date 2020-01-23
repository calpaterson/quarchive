from os import environ, path
from unittest.mock import patch

import pytest

import quarchive as sut

from .conftest import test_data_path


def test_load_config_with_incomplete_config():
    with patch.dict(environ, clear=True):
        with pytest.raises(RuntimeError) as e:
            sut.load_config()
        message = e.value.args[0]
        assert "QM_SQL_URL" in message


def test_load_config_with_test_config():
    with patch.dict(
        environ,
        {
            "QM_PASSWORD": "",
            "QM_SECRET_KEY": "",
            "QM_SQL_URL": "",
            "QM_RESPONSE_BODY_BUCKET_NAME": "",
            "QM_AWS_SECRET_ACCESS_KEY": "",
            "QM_AWS_ACCESS_KEY": "",
            "QM_AWS_REGION_NAME": "",
            "QM_AWS_S3_ENDPOINT_URL": "",
        },
        clear=True,
    ):
        sut.load_config()


def test_load_config_with_env_ini():
    with patch.dict(environ, clear=True):
        sut.load_config(env_ini=path.join(test_data_path, "env.ini"))
        for key in sut.REQUIRED_CONFIG_KEYS:
            assert key in environ


def test_load_config_with_incomplete_env_ini():
    with patch.dict(environ, clear=True):
        with pytest.raises(RuntimeError) as e:
            sut.load_config(env_ini=path.join(test_data_path, "incomplete-env.ini"))
