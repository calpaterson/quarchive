from typing import Dict, Any
from os import environ
from sys import stderr
import logging

from systemd.journal import JournalHandler

# logging module doesn't provide an easy way to get this
LOG_LEVELS = [
    "CRITICAL",
    "ERROR",
    "WARNING",
    "INFO",
    "DEBUG",
]


def reduce_boto_logging():
    # AWS provided libraries have extremely verbose debug logs
    boto_loggers = ["boto3", "botocore", "s3transfer"]
    for boto_logger in boto_loggers:
        logging.getLogger(boto_logger).setLevel(logging.INFO)


def configure_logging(level: str = "INFO"):
    """Configure our logging - stderr by default but logging nicely the journal
    under systemd."""
    under_systemd = "INVOCATION_ID" in environ
    kwargs: Dict[str, Any] = dict(level=level)
    if under_systemd:
        kwargs["format"] = "%(message)s"
        kwargs["handlers"] = [JournalHandler()]
    else:
        kwargs["format"] = "%(asctime)s %(levelname)-8s %(name)-35s - %(message)s"
        kwargs["stream"] = stderr
    logging.basicConfig(**kwargs)
    reduce_boto_logging()
