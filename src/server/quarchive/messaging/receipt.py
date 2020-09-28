from typing import Optional, Any
import pickle

import missive


class PickleMessage(missive.Message):
    """The internal message format is pickle (for now)."""

    def __init__(self, raw_data: bytes) -> None:
        self._obj: Optional[Any] = None

    def get_obj(self) -> Any:
        if self._obj is None:
            self._obj = pickle.loads(self.raw_data)
        return self._obj
