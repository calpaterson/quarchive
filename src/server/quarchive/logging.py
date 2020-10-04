from sys import stderr
import logging

FORMAT = "%(asctime)s %(levelname)-8s %(name)-30s - %(message)s"

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
    """Configure logging with our standard format, and to stderr"""
    logging.basicConfig(level=level, format=FORMAT, stream=stderr)
    reduce_boto_logging()
