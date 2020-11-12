import logging

import pytest
from missive import TestAdapter

from quarchive.messaging.receipt import PickleMessage
from quarchive.messaging.message_lib import HelloEvent


def test_hello_event(bg_client: TestAdapter[PickleMessage], caplog):
    caplog.set_level(logging.INFO, logger="quarchive.bg_worker")
    event = HelloEvent("greetings earthling")
    bg_client.send(PickleMessage.from_obj(event))
    logs = [r.getMessage() for r in caplog.records]
    expected = "greetings earthling"
    # FIXME: this is pretty ropey and fragile
    assert expected in logs[-1]
