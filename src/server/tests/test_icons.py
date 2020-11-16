from uuid import UUID
from os import path

from PIL import Image
import flask
import pytest

from quarchive.icons import convert_icon

from .conftest import test_data_path


def test_get_icon(client):
    response = client.get(
        flask.url_for("quarchive.icon_by_uuid", icon_uuid=UUID("f" * 32))
    )
    assert response.status_code == 501


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
