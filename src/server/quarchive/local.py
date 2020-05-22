import logging

from quarchive.web.app import init_app


def main() -> None:
    app = init_app()
    logging.basicConfig(level=logging.INFO)
    app.run()
