from typing import TypeVar, Generic, IO
from contextlib import AbstractContextManager


I = TypeVar("I", bound=IO[bytes])


class RewindingIO(Generic[I], AbstractContextManager):
    """A self-rewinding (binary) IO.

    Useful because there are a lot of places where a (usually temporary) file
    is passed over a number of times.

    """

    def __init__(self, io: I):
        self.io = io
        self.rewind()

    def rewind(self):
        """Rewind the inner IO back to the start (ready for reuse)"""
        self.io.seek(0)

    def __enter__(self) -> I:
        return self.io

    def __exit__(self, exctype, excvalue, traceback) -> None:
        self.rewind()

    def __repr__(self):
        return f"<RewindingIO ({repr(self.io)}))>"
