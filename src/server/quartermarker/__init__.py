from dataclasses import dataclass
import logging

import flask
from flask_cors import CORS

log = logging.getLogger("quartermarker")


@dataclass
class Bookmark:
    url: str

    def merge(self, other):
        log.info("merging %s + %s -> %s", self, other, self)
        return self


app = flask.Flask("quartermarker")
CORS(app)


@app.route("/ok")
def ok():
    return flask.json.jsonify({"ok": True})


@app.route("/sync")
def sync():
    raise NotImplementedError


def main():
    logging.basicConfig(level=logging.INFO)
    app.run()
