from typing import IO
from tempfile import TemporaryFile

from PIL import Image


def convert_icon(filelike: IO[bytes]) -> IO[bytes]:
    """Convert the input image into a 32x32 PNG"""
    image = Image.open(filelike)
    temp_file = TemporaryFile()
    resized = image.resize((32, 32), resample=Image.LANCZOS)
    resized.save(temp_file, format="png", optimize=True)
    temp_file.seek(0)
    return temp_file
