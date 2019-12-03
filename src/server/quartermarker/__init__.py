from dataclasses import dataclass
import logging
from typing import MutableMapping, Mapping, Set

import flask
from flask_cors import CORS

log = logging.getLogger("quartermarker")


@dataclass(frozen=True)
class Bookmark:
    url: str

    def merge(self, other):
        log.info("merging %s + %s -> %s", self, other, self)
        return self

    def to_json(self) -> Mapping:
        return {"url": self.url}


app = flask.Flask("quartermarker")
CORS(app)

DATA_STORE: MutableMapping[str, Bookmark] = {}


@app.route("/ok")
def ok():
    return flask.json.jsonify({"ok": True})


@app.route("/sync", methods=["POST"])
def sync():
    body = flask.request.json
    recieved_bookmarks: Set[Bookmark] = set(
        Bookmark(url=item["url"]) for item in body["bookmarks"]
    )
    merged_bookmarks: Set[Bookmark] = set()
    new_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        if recieved.url in DATA_STORE:
            existing = DATA_STORE[recieved.url]
            merged = existing.merge(recieved)
            if merged != existing:
                merged_bookmarks.add(merged)
                log.info("merged: %s + %s = %s", recieved, existing, merged)
            else:
                log.info("no change to %s", recieved)
        else:
            new_bookmarks.add(recieved)
            DATA_STORE[recieved.url] = recieved
            log.info("added: %s", recieved)
    changed_bookmarks = merged_bookmarks.difference(recieved_bookmarks)
    return flask.json.jsonify({"bookmarks": [b.to_json() for b in changed_bookmarks]})


def main():
    logging.basicConfig(level=logging.INFO)
    app.run()
