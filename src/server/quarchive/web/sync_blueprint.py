import json
from functools import wraps
from logging import getLogger
from datetime import datetime
from typing import cast, TypeVar, Callable, Tuple
from os import environ

import flask

from quarchive.cache import get_cache
from quarchive.data.functions import (
    is_correct_api_key,
    user_from_username_if_exists,
    merge_bookmarks,
    all_bookmarks,
)
from quarchive.messaging import message_lib
from quarchive.messaging.publication import publish_message
from quarchive.value_objects import User, Bookmark, BadCanonicalisationException
from .db_obj import db
from .users import get_current_user

log = getLogger(__name__)

sync_blueprint = flask.Blueprint("quarchive-sync", "quarchive-sync")

V = TypeVar("V", bound=Callable)


def api_key_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            # FIXME: Remove old synonyms
            username = (
                flask.request.headers.get("X-QM-API-Username")
                or flask.request.headers["Quarchive-Username"]
            )
            api_key_str = (
                flask.request.headers.get("X-QM-API-Key")
                or flask.request.headers["Quarchive-API-Key"]
            )
        except KeyError:
            flask.current_app.logger.info("no api credentials")
            return flask.jsonify({"error": "no api credentials"}), 400

        cache = get_cache()

        try:
            api_key = bytes.fromhex(api_key_str)
        except ValueError:
            flask.current_app.logger.warning("invalid api key: %s", username)
            return (
                flask.jsonify({"error": "invalid api key (should be hexadecimal)"}),
                400,
            )

        if is_correct_api_key(db.session, cache, username, api_key):
            # We know at this point that the user does in fact exist, so cast
            # away the Optional
            user = cast(User, user_from_username_if_exists(db.session, cache, username))
            # FIXME: This should perhaps user .users.set_current_user, somehow
            flask.g.user = user
            return handler()
        else:
            # Something was wrong, let's figure out what
            user_if_exists = user_from_username_if_exists(db.session, cache, username)
            if user_if_exists is None:
                flask.current_app.logger.warning("user does not exist: %s", username)
                # user doesn't exist
                return flask.jsonify({"error": "user does not exist"}), 400
            else:
                flask.current_app.logger.warning("wrong api key for %s", username)
                # api key must have been wrong
                return flask.jsonify({"error": "wrong api key"}), 400

    return cast(V, wrapper)


@sync_blueprint.route("/api/sync/check-api-key", methods=["POST"])
@api_key_required
def sync_check_api_key() -> Tuple[flask.Response, int]:
    return flask.jsonify({}), 200


@sync_blueprint.route("/api/sync", methods=["POST"])
@sync_blueprint.route("/sync", methods=["POST"])  # FIXME: Deprecated
@api_key_required
def sync() -> flask.Response:
    start_time = datetime.utcnow()
    extension_version = flask.request.headers.get(
        "Quarchive-Extension-Version", "unknown"
    )
    log.debug("extension version: %s", extension_version)
    user = get_current_user()
    user_uuid = user.user_uuid
    use_jsonlines = flask.request.headers["Content-Type"] != "application/json"
    if not use_jsonlines:
        log.warning("sync request using deprecated single json object")
        body = flask.request.json
        recieved_bookmarks = (Bookmark.from_json(item) for item in body["bookmarks"])
    else:
        log.info("sync request using jsonlines")
        recieved_bookmarks = (
            Bookmark.from_json(json.loads(l)) for l in flask.request.stream.readlines()
        )

    try:
        merge_result = merge_bookmarks(db.session, user_uuid, recieved_bookmarks)
    except BadCanonicalisationException as e:
        log.error(
            "bad canonicalised url ('%s') from version %s, user %s",
            e.url_string,
            extension_version,
            user,
        )
        db.session.rollback()
        flask.abort(400, "bad canonicalisation on url: %s" % e.url_string)
    db.session.commit()

    for added in merge_result.added:
        publish_message(
            message_lib.BookmarkCreated(
                user_uuid=user_uuid, url_uuid=added.url.url_uuid
            ),
            environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
        )

    is_full_sync = "full" in flask.request.args

    if is_full_sync:
        response_bookmarks = all_bookmarks(db.session, get_current_user().user_uuid)
    else:
        response_bookmarks = merge_result.changed

    # If we got JSON, send json back
    if not use_jsonlines:
        return flask.json.jsonify(
            {"bookmarks": [b.to_json() for b in response_bookmarks]}
        )
    else:

        def generator():
            for b in response_bookmarks:
                yield json.dumps(b.to_json())
                yield "\n"
            if is_full_sync:
                duration = datetime.utcnow() - start_time
                log.info(
                    "completed full sync for %s in %ds",
                    user.username,
                    duration.total_seconds(),
                )

        return flask.Response(
            flask.stream_with_context(generator()), mimetype="application/x-ndjson",
        )
