from uuid import UUID, uuid4
from os import path

from PIL import Image
import flask
import pytest

from quarchive import file_storage
from quarchive.icons import convert_icon

from .conftest import test_data_path


def test_get_icon(client, mock_s3):
    icon_uuid = uuid4()
    with open(
        path.join(test_data_path, "wikipedia-32px.png"), "r+b"
    ) as wikipedia_icon_f:
        file_storage.upload_icon(
            file_storage.get_icon_bucket(), icon_uuid, wikipedia_icon_f
        )

    response = client.get(flask.url_for("quarchive.icon_by_uuid", icon_uuid=icon_uuid))
    assert response.status_code == 200


@pytest.mark.xfail(reason="not implemented")
def test_get_icon_404(client, mock_s3):
    assert False


@pytest.mark.parametrize(
    "image_file_name",
    [
        "wikipedia.ico",
        "wikipedia-16px.png",
        "wikipedia-32px.png",
        "wikipedia-48px.png",
    ],
)
def test_convert_icon(image_file_name):
    with open(path.join(test_data_path, image_file_name), "rb") as ico_f:
        converted_icon = convert_icon(ico_f)

    image = Image.open(converted_icon)
    assert image.size == (32, 32)
    assert image.format == "PNG"
