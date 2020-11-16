import os
from typing import IO
from tempfile import NamedTemporaryFile
import subprocess

from PIL import Image

DEVNULL = open(os.devnull, "w")


def convert_icon(filelike: IO[bytes]) -> IO[bytes]:
    """Convert the input image into a (crushed) 32x32 PNG.

    Crushing is important because there will be a lot of these images and we
    want to keep them small to reduce s3 costs and ensure that they are
    retained in HTTP caches as long as possible."""
    image = Image.open(filelike)

    # Created a named temporary file, with auto deletion off
    try:
        temp_file = NamedTemporaryFile(
            mode="r+b", delete=False, prefix="quarchive-tmp-icon-", suffix=".png"
        )

        resized = image.resize((32, 32), resample=Image.LANCZOS)
        resized.save(temp_file, format="png")

        # Close the handle to write out new image file to the fs
        temp_file.close()

        # pngcrush does a lot better than PIL at optimizing (50% or more)
        result = subprocess.run(
            ["pngcrush", "-ow", temp_file.name], stdout=DEVNULL, stderr=DEVNULL
        )

        # Raise an exception if something went wrong
        result.check_returncode()

        # Open a handle to the new, crushed, png
        rv = open(temp_file.name, mode="r+b")
    finally:
        # then delete the underlying file
        os.remove(temp_file.name)

    return rv
