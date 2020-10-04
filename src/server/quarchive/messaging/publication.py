from logging import getLogger
from os import environ
import pickle

import click
import kombu

from quarchive.logging import LOG_LEVELS, configure_logging
from .message_lib import Event, HelloEvent

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
    return _producer


def publish_message(message: Event, routing_key: str) -> None:
    producer = get_producer()
    producer.publish(
        pickle.dumps(message, protocol=PICKLE_PROTOCOL), routing_key=routing_key
    )
    log.info("published %s message to with %s", message, routing_key)


@click.command()
@click.argument("message")
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
@click.option(
    "--loop", is_flag=True, help="send the message repeatedly (as a load generator)"
)
def send_hello(message, loop, log_level):
    configure_logging(log_level)
    routing_key: str = environ["QM_RABBITMQ_BG_WORKER_TOPIC"]

    # call this for side-effects - to ensure things are set up so that the timing numbers are accurate
    get_producer()

    hello_event = HelloEvent(message)
    publish_message(hello_event, routing_key=routing_key)
    if loop:
        while True:
            hello_event = HelloEvent(message)
            publish_message(hello_event, routing_key=routing_key)
