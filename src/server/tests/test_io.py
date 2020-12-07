import tempfile
from io import BytesIO
from quarchive.io import RewindingIO

import pytest


def test_rewinding_io():
    rewinding_io = RewindingIO(tempfile.TemporaryFile())

    with rewinding_io as filelike:
        filelike.write(b"hello, world!")

    with rewinding_io as filelike:
        assert filelike.read() == b"hello, world!"


def test_rewinding_io_with_exception():
    rewinding_io = RewindingIO(tempfile.TemporaryFile())
    with pytest.raises(RuntimeError):
        with rewinding_io as filelike:
            filelike.write(b"foo")
            raise RuntimeError("no!")


def test_rewinding_io_repr():
    sub_io = BytesIO(b"test")
    rewinding_io = RewindingIO(sub_io)
    assert str(rewinding_io).startswith("<RewindingIO ")
    assert repr(rewinding_io).startswith("<RewindingIO ")
