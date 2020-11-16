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


def turn_down_noisy_loggers():
    # Some libraries (particularly Amazon's) have extremely verbose debug logs
    noisy_loggers = ["boto3", "botocore", "s3transfer", "PIL"]
    for logger in noisy_loggers:
        logging.getLogger(logger).setLevel(logging.INFO)


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
    turn_down_noisy_loggers()
