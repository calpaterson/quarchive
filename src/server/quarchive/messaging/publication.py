from logging import getLogger
from os import environ
import pickle

import kombu

from .message_lib import Event

_connection = None

log = getLogger(__name__)

PICKLE_PROTOCOL = 4


def get_connection():
    global _connection
    if _connection is None:
        _connection = kombu.Connection(environ["QM_RABBITMQ_URL"])
        log.info("opened connection to %s", _connection.as_uri())
    return _connection


_channel = None


def get_channel():
    global _channel
    if _channel is None:
        _channel = get_connection().channel()
        log.info("created channel %d", _channel.channel_id)
    return _channel


_producer = None


def get_producer():
    global _producer
    if _producer is None:
        _producer = kombu.Producer(get_channel())
        log.debug("created producer %s", _producer)
    return _producer


def publish_message(message: Event, routing_key: str) -> None:
    producer = get_producer()
    producer.publish(
        pickle.dumps(message, protocol=PICKLE_PROTOCOL), routing_key=routing_key
    )
    log.debug("published %s message to with %s", message, routing_key)
