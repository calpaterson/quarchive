from os import environ
from datetime import datetime, timezone
from typing import Type, cast
from logging import getLogger, basicConfig, INFO

import click
import missive
from missive.adapters.rabbitmq import RabbitMQAdapter

from quarchive.messaging.message_lib import Event, HelloEvent
from quarchive.messaging.receipt import PickleMessage

log = getLogger(__name__)


processor: missive.Processor[PickleMessage] = missive.Processor()


class ClassMatcher:
    def __init__(self, required_class: Type[Event]):
        self.required_class = required_class

    def __call__(self, message: PickleMessage) -> bool:
        return isinstance(message.get_obj(), self.required_class)


@processor.handle_for([ClassMatcher(HelloEvent)])
def print_hellos(message: PickleMessage, ctx: missive.HandlingContext):
    event: HelloEvent = cast(HelloEvent, message.get_obj())
    time_taken_ms = (datetime.now(timezone.utc) - event.created).total_seconds() * 1000
    log.info(
        "got hello event (in %.3fms), message: '%s'",
        round(time_taken_ms, 3),
        event.message,
    )
    ctx.ack(message)


@click.command()
def bg_worker():
    basicConfig(level=INFO)
    adapted_processor = RabbitMQAdapter(
        PickleMessage,
        processor,
        environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
        url=environ["QM_RABBITMQ_URL"],
    )
    adapted_processor.run()
