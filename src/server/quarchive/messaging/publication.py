from logging import getLogger, basicConfig, INFO
from os import environ
import pickle

import click
import kombu

from .message_lib import Event, HelloEvent

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
        _producer = kombu.Producer(get_channel())
    return _producer


def publish_message(message: Event, routing_key: str) -> None:
    producer = get_producer()
    producer.publish(pickle.dumps(message), routing_key=routing_key)
    log.info("published %s message to with %s", message, routing_key)


@click.command()
@click.argument("message")
def send_hello(message):
    basicConfig(level=INFO)
    get_producer()  # call this for side-effects - to ensure things are set up
    hello_event = HelloEvent(message)
    publish_message(hello_event, routing_key=environ["QM_RABBITMQ_BG_WORKER_TOPIC"])
