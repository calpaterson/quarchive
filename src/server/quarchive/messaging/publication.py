from logging import getLogger
from os import environ
from typing import Any
import pickle

import kombu

_connection = None

log = getLogger()


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
        _producer = kombu.Producer(_channel)
    return _producer


def publish_message(message: Any, routing_key: str) -> None:
    producer = get_producer()
    producer.publish(pickle.dumps(message), routing_key=routing_key)
