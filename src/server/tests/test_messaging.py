from uuid import uuid4
import pickle

import kombu
import pytest

from quarchive.messaging.receipt import PickleMessage
from quarchive.messaging.message_lib import BookmarkCreated
from quarchive.messaging.publication import publish_message, get_channel

from .conftest import random_string


@pytest.fixture(scope="function")
def test_queue(config):
    queue_name = "test-%s" % random_string()
    channel = get_channel()
    queue = kombu.Queue(name=queue_name, channel=channel)
    queue.declare()
    yield queue
    queue.delete()


def test_publish_message(test_queue):
    """Test that simple sending of messages works correctly"""
    sent_message = BookmarkCreated(uuid4(), uuid4())
    publish_message(sent_message, routing_key=test_queue.name)

    received_message = pickle.loads(test_queue.get().body)
    assert received_message == sent_message
