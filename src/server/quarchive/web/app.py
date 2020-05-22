import logging
from functools import lru_cache
from os import environ
from urllib.parse import urlunsplit

import flask
import pyhash
from flask_babel import Babel
from flask_cors import CORS
from passlib.context import CryptContext
from werkzeug.urls import url_encode

from quarchive.config import load_config

from .blueprint import blueprint
from .db_obj import db

log = logging.getLogger(__name__)

cors = CORS()


@lru_cache(1)
def get_hasher():
    return pyhash.fnv1_32()


@lru_cache()
def tag_colour(tag: str) -> int:
    return get_hasher()(tag) % 5


def init_app() -> flask.Flask:
    load_config(env_ini=environ.get("QM_ENV_INI", None))
    app = flask.Flask("quarchive")
    app.config["SECRET_KEY"] = environ["QM_SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"] = environ["QM_SQL_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["CRYPT_CONTEXT"] = CryptContext(["bcrypt"])

    # By default Postgres will consult the locale to decide what timezone to
    # return datetimes in.  We want UTC in all cases.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"options": "-c timezone=utc"}
    }

    app.config["PAGE_SIZE"] = 30
    db.init_app(app)
    with app.app_context():
        log.info("using engine: %s", db.session.bind)

    cors.init_app(app)
    Babel(app, default_locale="en_GB", default_timezone="Europe/London")
    app.register_blueprint(blueprint)

    @app.context_processor
    def urlsplit_cp():
        return {"urlunsplit": urlunsplit}

    @app.template_global(name="tag_colour")
    def tag_colour_template_function(tag: str) -> int:
        return tag_colour(tag)

    @app.template_global(name="modify_query")
    def modify_query(**new_args):
        args = flask.request.args.copy()

        for key, value in new_args.items():
            if value is not None:
                args[key] = value
            else:
                # None is a request to unset
                del args[key]

        return "?%s" % url_encode(args)

    return app
