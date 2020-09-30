from typing import Optional, Any
import pickle

import missive

from .message_lib import Event


class PickleMessage(missive.Message):
    """The internal message format is pickle (for now)."""

    protocol_version: int = 4

    def __init__(self, raw_data: bytes) -> None:
        super().__init__(raw_data)
        self._obj: Optional[Any] = None
        self.raw_data = raw_data

    def get_obj(self) -> Event:
        if self._obj is None:
            self._obj = pickle.loads(self.raw_data)
        return self._obj

    @classmethod
    def from_obj(cls, obj) -> "PickleMessage":
        return PickleMessage(pickle.dumps(obj, protocol=4))
