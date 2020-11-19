import os
from typing import IO
from tempfile import NamedTemporaryFile
import subprocess
from logging import getLogger

from PIL import Image

log = getLogger(__name__)

DEVNULL = open(os.devnull, "w")


def convert_icon(filelike: IO[bytes]) -> IO[bytes]:
    """Convert the input image (often ICO format) into a (crushed) 32x32 PNG.

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
        initial_size = temp_file.tell()

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

        # Log out the size reduction
        rv.seek(0, 2)
        crushed_size = rv.tell()
        rv.seek(0)
        log.debug("reduced image from %d bytes to %d", initial_size, crushed_size)

    finally:
        # then delete the underlying file (existing handle will continue to
        # work due to CoW
        os.remove(temp_file.name)

    return rv
