import logging

import click

from quarchive.logging import LOG_LEVELS, configure_logging
from quarchive.web.app import init_app


@click.command()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="INFO")
def main(log_level) -> None:
    configure_logging(log_level)
    app = init_app()
    app.run()
