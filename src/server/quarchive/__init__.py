import re
import configparser
import contextlib
from datetime import datetime, timezone
import gzip
from functools import wraps, lru_cache
import itertools
import logging
import mimetypes
from uuid import UUID, uuid4
from typing import (
    Dict,
    Mapping,
    Sequence,
    Set,
    FrozenSet,
    Any,
    Optional,
    Callable,
    Iterable,
    MutableSequence,
    cast,
    TypeVar,
    Tuple,
    BinaryIO,
    List,
    Union,
    TYPE_CHECKING,
)
from os import environ, path
from urllib.parse import urlsplit, urlunsplit
import json
import tempfile
import shutil
from abc import ABCMeta, abstractmethod
import cgi
import secrets

import yaml
import pyhash
from passlib.context import CryptContext
import lxml
import lxml.html
import click
import boto3
from botocore.utils import fix_s3_host
import requests
from celery import Celery
from werkzeug import exceptions as exc
from werkzeug.urls import url_encode
from dateutil.parser import isoparse
from sqlalchemy import (
    Column,
    ForeignKey,
    types as satypes,
    func,
    create_engine,
    and_,
    cast as sa_cast,
)
from sqlalchemy.orm import (
    foreign,
    remote,
    relationship,
    RelationshipProperty,
    Session,
    sessionmaker,
    scoped_session,
)
from sqlalchemy.dialects.postgresql import (
    UUID as _PGUUID,
    insert as pg_insert,
    BYTEA,
    JSONB,
    TSVECTOR,
    array as pg_array,
    ARRAY as PGARRAY,
)
from flask_sqlalchemy import SQLAlchemy
import flask
from flask_cors import CORS
import missive
from missive.adapters.rabbitmq import RabbitMQAdapter
from flask_babel import Babel
import magic

from .value_objects import (
    Bookmark,
    URL,
    User,
    TagTriples,
    bookmark_from_sqla,
)
from .data.models import (
    SQLAUrl,
    SQLABookmark,
    SQLUser,
    FullText,
    CrawlRequest,
    CrawlResponse,
)
from .data.functions import (
    is_correct_api_key,
    get_api_key,
    username_exists,
    user_from_username,
    user_from_user_uuid,
    create_user,
    get_bookmark_by_url,
    get_bookmark_by_url_uuid,
    upsert_url,
    set_bookmark,
    merge_bookmarks,
    all_bookmarks,
    bookmarks_with_tag,
    tags_with_count,
)


# https://github.com/dropbox/sqlalchemy-stubs/issues/94
if TYPE_CHECKING:
    PGUUID = satypes.TypeEngine[UUID]
else:
    PGUUID = _PGUUID(as_uuid=True)

log = logging.getLogger("quarchive")

# fmt: off
# Config loading
...
# fmt: on

REQUIRED_CONFIG_KEYS = {
    "QM_SQL_URL",
    "QM_SECRET_KEY",
    "QM_RESPONSE_BODY_BUCKET_NAME",
    "QM_AWS_ACCESS_KEY",
    "QM_AWS_REGION_NAME",
    "QM_AWS_SECRET_ACCESS_KEY",
    "QM_AWS_S3_ENDPOINT_URL",
}


def load_config(env_ini: Optional[str] = None) -> None:
    if env_ini is not None:
        log.info("loading from %s", path.abspath(env_ini))
        parser = configparser.ConfigParser()
        # mypy confused by this unusual pattern
        # https://github.com/python/mypy/issues/708
        parser.optionxform = str  # type: ignore
        parser.read(env_ini)
        environ.update(parser["env"].items())
    else:
        log.warning("not loading env from any config file")

    if not REQUIRED_CONFIG_KEYS.issubset(set(environ.keys())):
        missing_keys = REQUIRED_CONFIG_KEYS.difference(set(environ.keys()))
        raise RuntimeError("incomplete configuration! missing keys: %s" % missing_keys)


# fmt: off
# # Web layer
...
# fmt: on

db = SQLAlchemy()
cors = CORS()
blueprint = flask.Blueprint("quarchive", "quarchive")


# Flask's "views" are quite variable
V = TypeVar("V", bound=Callable)


def get_current_user() -> User:
    """Utility function to get the current user.

    The only purpose of this is for typing - flask.g.user is unavoidably Any
    whereas the return type of this is User.

    """
    return flask.g.user


@blueprint.before_request
def put_user_in_g() -> None:
    user_uuid: Optional[UUID] = flask.session.get("user_uuid")
    if user_uuid is not None:
        flask.g.user = user_from_user_uuid(db.session, user_uuid)
        flask.current_app.logger.debug("currently signed in as: %s", flask.g.user)
    else:
        flask.current_app.logger.debug("not signed in")


@blueprint.before_app_first_request
def log_db() -> None:
    flask.current_app.logger.info("using engine: %s", db.session.bind)


def sign_in_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if flask.g.get("user", None) is None:
            # FIXME: This should use redirect_to
            return flask.redirect("/sign-in"), 302
        else:
            return handler(*args, **kwargs)

    return cast(V, wrapper)


def observe_redirect_to(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        response = handler(*args, **kwargs)
        if response.status_code == 200 and "redirect_to" in flask.request.args:
            redirection = flask.make_response("redirecting",)
            redirection.headers["Location"] = flask.request.args["redirect_to"]
            return redirection, 303
        else:
            return response

    return cast(V, wrapper)


def api_key_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            username = flask.request.headers["X-QM-API-Username"]
            api_key_str = flask.request.headers["X-QM-API-Key"]
        except KeyError:
            flask.current_app.logger.info("no api credentials")
            return flask.jsonify({"error": "no api credentials"}), 400

        if is_correct_api_key(db.session, username, bytes.fromhex(api_key_str)):
            flask.g.user = user_from_username(db.session, username)
            return handler()
        else:
            flask.current_app.logger.info("bad api credentials")
            return flask.jsonify({"error": "bad api credentials"}), 400

    return cast(V, wrapper)


@blueprint.route("/about")
def about() -> flask.Response:
    return flask.make_response(
        flask.render_template("about.html", page_title="About Quarchive")
    )


@blueprint.route("/")
@sign_in_required
def my_bookmarks() -> Tuple[flask.Response, int]:
    # FIXME: This viewfunc really needs to get split up and work via the data
    # layer to get what it wants.
    page_size = flask.current_app.config["PAGE_SIZE"]
    page = int(flask.request.args.get("page", "1"))
    offset = (page - 1) * page_size
    user = get_current_user()
    query = db.session.query(SQLABookmark).filter(
        SQLABookmark.user_uuid == user.user_uuid
    )

    if "q" in flask.request.args:
        query = query.outerjoin(FullText, FullText.url_uuid == SQLABookmark.url_uuid)

        search_str = flask.request.args["q"]
        tquery_str = parse_search_str(search_str)
        log.debug('search_str, tquery_str = ("%s", "%s")', search_str, tquery_str)

        # necessary to coalesce this as there may be no fulltext
        fulltext = func.coalesce(FullText.tsvector, func.to_tsvector(""))

        combined_tsvector = (
            func.to_tsvector(SQLABookmark.title)
            .op("||")(func.to_tsvector(SQLABookmark.description))
            .op("||")(fulltext)
        )
        tsquery = func.to_tsquery(tquery_str)
        query = query.filter(combined_tsvector.op("@@")(tsquery))
        query = query.order_by(func.ts_rank(combined_tsvector, tsquery, 1))
        page_title = search_str
    else:
        page_title = "Quarchive"

    if page > 1:
        page_title += " (page %s)" % page

    # omit deleted bookmarks
    query = query.filter(~SQLABookmark.deleted)

    sqla_objs = (
        query.order_by(SQLABookmark.created.desc()).offset(offset).limit(page_size)
    )

    prev_page_exists = page > 1
    next_page_exists: bool = db.session.query(
        query.order_by(SQLABookmark.created.desc()).offset(offset + page_size).exists()
    ).scalar()

    bookmarks = []
    for sqla_obj in sqla_objs:
        url = URL.from_sqla_url(sqla_obj.url_obj)
        bookmarks.append((url, bookmark_from_sqla(url.to_url(), sqla_obj)))
    return flask.make_response(
        flask.render_template(
            "my_bookmarks.html",
            page_title=page_title,
            bookmarks=bookmarks,
            page=page,
            prev_page_exists=prev_page_exists,
            next_page_exists=next_page_exists,
            q=flask.request.args.get("q"),
        )
    )


def form_fields_from_querystring(
    querystring: Mapping[str, str],
) -> Mapping[str, Union[str, List[str]]]:
    """Examine the querystring passed to the create or edit bookmark form and
    return a mapping representing the form fields to fill."""
    form_fields: Dict[str, Union[str, List[str]]] = {}

    simple_fields = {"url", "title", "description"}
    for field_name in simple_fields:
        field_value = querystring.get(field_name, "")
        if field_value != "":
            form_fields[field_name] = field_value

    unread_value = querystring.get("unread", None) or None
    if unread_value is not None:
        form_fields["unread"] = unread_value

    raw_tags: str = querystring.get("tags", "").strip()
    add_tag: Optional[str] = querystring.get("add-tag", "").strip() or None
    remove_tag: Optional[str] = querystring.get("remove-tag", "").strip() or None
    if raw_tags != "" or add_tag is not None:
        tags: Set[str]
        if raw_tags == "":
            tags = set()
        else:
            tags = set(raw_tags.split(","))

        if add_tag is not None:
            tags.add(add_tag)

        if remove_tag is not None:
            tags.remove(remove_tag)
        form_fields["tags"] = sorted(tags)

    log.debug(
        "calculated form fields: %s from querystring %s", form_fields, querystring
    )
    return form_fields


@blueprint.route("/create-bookmark")
@sign_in_required
def create_bookmark_form() -> flask.Response:
    template_kwargs: Dict[str, Any] = {"page_title": "Create bookmark"}
    template_kwargs.update(form_fields_from_querystring(flask.request.args))
    template_kwargs["tags_with_count"] = tags_with_count(db.session, get_current_user())

    return flask.make_response(
        flask.render_template("create_bookmark.html", **template_kwargs)
    )


@blueprint.route("/bookmark/<uuid:url_uuid>", methods=["GET"])
@sign_in_required
@observe_redirect_to
def edit_bookmark_form(url_uuid: UUID) -> flask.Response:
    bookmark = get_bookmark_by_url_uuid(
        db.session, get_current_user().user_uuid, url_uuid
    )
    if bookmark is None:
        # FIXME: er, write a test for this
        flask.abort(404, description="bookmark not found")

    # Step one, load the template kwargs from the bookmark
    template_kwargs: Dict[str, Any] = dict(
        url=bookmark.url,
        title=bookmark.title,
        description=bookmark.description,
        page_title="Edit %s" % bookmark.title,
        url_uuid=url_uuid,
        tags=bookmark.current_tags(),
    )
    if bookmark.unread:
        template_kwargs["unread"] = "on"

    # Then update it from the querystring
    template_kwargs.update(form_fields_from_querystring(flask.request.args))

    template_kwargs["tags_with_count"] = tags_with_count(db.session, get_current_user())
    template_kwargs["deleted"] = bookmark.deleted

    return flask.make_response(
        flask.render_template("edit_bookmark.html", **template_kwargs)
    )


def tag_triples_from_form(
    form: Mapping[str, str], current: TagTriples = frozenset()
) -> TagTriples:
    """Parse a form for tag triples, consulting the hidden "tags" field and
    considering which tags are expected (if any are missing, they have been
    implicitly deleted)."""
    current_as_map = {tt[0]: tt for tt in current}

    raw_tags = flask.request.form["tags"].strip()
    form_tags: Set[str]
    if raw_tags == "":
        form_tags = set()
        log.debug("no tags present in form")
    else:
        form_tags = set(raw_tags.split(","))

    now = datetime.utcnow().replace(tzinfo=timezone.utc)

    return_value = set()
    all_tags = set(current_as_map.keys()).union(set(form_tags))
    for tag_name in all_tags:
        if tag_name in current_as_map and tag_name in form_tags:
            _, dt, deleted = current_as_map[tag_name]
            if not deleted:
                # no change
                return_value.add((tag_name, dt, False))
            else:
                # has been undeleted
                return_value.add((tag_name, now, False))
        elif tag_name in current_as_map and tag_name not in form_tags:
            # has been deleted
            return_value.add((tag_name, now, True))
        else:  # tag_name not in current_map and tag_name in form_tags:
            # has been created
            return_value.add((tag_name, now, False))

    log.debug(
        "calculated tag_triples: %s from raw_tags: '%s' (current: %s)",
        return_value,
        raw_tags,
        current,
    )
    return frozenset(return_value)


@blueprint.route("/bookmark", methods=["POST"])
@sign_in_required
def create_bookmark() -> flask.Response:
    form = flask.request.form
    creation_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    tag_triples = tag_triples_from_form(form)
    bookmark = Bookmark(
        url=form["url"],
        title=form["title"],
        description=form["description"],
        unread="unread" in form,
        deleted=False,
        updated=creation_time,
        created=creation_time,
        tag_triples=tag_triples,
    )
    url_uuid = set_bookmark(db.session, get_current_user().user_uuid, bookmark)
    db.session.commit()
    flask.flash("Bookmarked: %s" % bookmark.title)
    response = flask.make_response("Redirecting...", 303)
    response.headers["Location"] = flask.url_for(
        "quarchive.edit_bookmark_form", url_uuid=url_uuid
    )
    return response


@blueprint.route("/bookmark/<uuid:url_uuid>", methods=["POST"])
@sign_in_required
@observe_redirect_to
def edit_bookmark(url_uuid: UUID) -> flask.Response:
    form = flask.request.form
    existing_bookmark = get_bookmark_by_url_uuid(
        db.session, get_current_user().user_uuid, url_uuid
    )
    if existing_bookmark is None:
        raise exc.NotFound()

    updated_bookmark = Bookmark(
        url=existing_bookmark.url,
        created=existing_bookmark.created,
        title=form["title"],
        description=form["description"],
        unread="unread" in form,
        deleted="deleted" in form,
        updated=datetime.utcnow().replace(tzinfo=timezone.utc),
        tag_triples=tag_triples_from_form(form, current=existing_bookmark.tag_triples),
    )

    merged_bookmark = updated_bookmark.merge(existing_bookmark)

    set_bookmark(db.session, get_current_user().user_uuid, merged_bookmark)
    db.session.commit()
    flask.flash("Edited: %s" % merged_bookmark.title)
    return flask.make_response("ok")


@blueprint.route("/url/<uuid:url_uuid>")
@sign_in_required
def view_url(url_uuid: UUID) -> Tuple[flask.Response, int]:
    sqla_obj = db.session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url_uuid).first()
    if sqla_obj is None:
        raise exc.NotFound()
    else:
        url_obj = URL.from_sqla_url(sqla_obj)
        return flask.make_response(
            flask.render_template(
                "url.html", url=url_obj, page_title="View: %s" % url_obj.to_url()
            )
        )


@blueprint.route("/netloc/<string:netloc>")
@sign_in_required
def view_netloc(netloc: str) -> Tuple[flask.Response, int]:
    url_objs = db.session.query(SQLAUrl).filter(SQLAUrl.netloc == netloc)
    if url_objs.count() == 0:
        raise exc.NotFound()
    else:
        return flask.make_response(
            flask.render_template(
                "netloc.html",
                netloc=netloc,
                url_objs=url_objs,
                page_title="Netloc: %s" % netloc,
            )
        )


@blueprint.route("/register", methods=["GET", "POST"])
def register() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("register.html", page_title="Register")
        )
    else:
        username = flask.request.form["username"]
        password_plain = flask.request.form["password"]
        email: Optional[str] = flask.request.form["email"] or None

        if username_exists(db.session, username):
            log.error("username already registered: %s", username)
            flask.abort(400, description="username already exists")

        username_regex = r"^[A-z0-9_\-]+$"
        if not re.compile(username_regex).match(username):
            log.error("invalid username: %s", username)
            flask.abort(
                400, description="invalid username - must match %s" % username_regex
            )

        user_uuid = create_user(
            db.session,
            flask.current_app.config["CRYPT_CONTEXT"],
            username,
            password_plain,
            email,
        )

        db.session.commit()
        response = flask.make_response("Redirecting...", 303)
        response.headers["Location"] = flask.url_for("quarchive.my_bookmarks")
        log.info("created user: %s", username)
        flask.session["user_uuid"] = user_uuid
        return response


@blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("sign-in.html", page_title="Sign in")
        )
    else:
        crypt_context = flask.current_app.config["CRYPT_CONTEXT"]

        username = flask.request.form.get("username")
        user = db.session.query(SQLUser).filter(SQLUser.username == username).first()

        if user is None:
            flask.current_app.logger.info(
                "unsuccessful sign in - no such user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")

        password = flask.request.form.get("password")
        is_correct_password: bool = crypt_context.verify(password, user.password)
        if is_correct_password:
            flask.current_app.logger.info("successful sign in")
            flask.session["user_uuid"] = user.user_uuid

            # Make it last for 31 days
            flask.session.permanent = True
            flask.flash("Signed in")

            response = flask.make_response("Redirecting...", 303)
            response.headers["Location"] = "/"
            return response
        else:
            flask.current_app.logger.info(
                "unsuccessful sign in - wrong password for user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")


@blueprint.route("/sign-out", methods=["GET"])
def sign_out() -> flask.Response:
    flask.session.clear()
    flask.flash("Signed out")
    return flask.make_response(flask.render_template("base.html"))


@blueprint.route("/user/<username>")
def user_page(username: str) -> flask.Response:
    user = user_from_username(db.session, username)
    api_key: Optional[bytes]
    if user == flask.g.user:
        api_key = get_api_key(db.session, user.username)
    else:
        api_key = None
    return flask.make_response(
        flask.render_template("user.html", user=user, api_key=api_key,)
    )


@blueprint.route("/user/<username>/tags/<tag>")
@sign_in_required
def user_tag(username: str, tag: str) -> flask.Response:
    user = get_current_user()
    bookmarks = bookmarks_with_tag(db.session, user, tag)
    return flask.make_response(
        flask.render_template(
            "user_tag.html",
            bookmarks=bookmarks,
            tag=tag,
            page_title="Tagged as '%s'" % tag,
        )
    )


@blueprint.route("/user/<username>/tags")
@sign_in_required
def user_tags(username: str) -> flask.Response:
    user = get_current_user()
    tag_counts = tags_with_count(db.session, user)
    tt1 = list(tag_counts)
    return flask.make_response(
        flask.render_template("user_tags.html", tag_counts=tt1, page_title="My tags")
    )


@blueprint.route("/faq")
def faq() -> flask.Response:
    here = path.dirname(path.realpath(__file__))
    with open(path.join(here, "faq.yaml")) as faq_f:
        faq = yaml.safe_load(faq_f)

    return flask.make_response(flask.render_template("faq.html", faq=faq))


@blueprint.route("/ok")
def ok() -> flask.Response:
    return flask.json.jsonify({"ok": True})


@blueprint.route("/sync", methods=["POST"])
@api_key_required
def sync() -> flask.Response:
    log.debug(
        "extension version: %s",
        flask.request.headers.get("Quarchive-Extension-Version", "unknown"),
    )
    use_jsonlines = flask.request.headers["Content-Type"] != "application/json"

    if not use_jsonlines:
        log.warning("sync request using deprecated single json object")
        body = flask.request.json
        recieved_bookmarks = set(Bookmark.from_json(item) for item in body["bookmarks"])
    else:
        log.info("sync request using jsonlines")
        recieved_bookmarks = set(
            Bookmark.from_json(json.loads(l)) for l in flask.request.stream.readlines()
        )

    changed_bookmarks = merge_bookmarks(
        db.session, get_current_user().user_uuid, recieved_bookmarks
    )
    db.session.commit()
    if "full" in flask.request.args:
        response_bookmarks = all_bookmarks(db.session, get_current_user().user_uuid)
    else:
        response_bookmarks = changed_bookmarks

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

        return flask.Response(
            flask.stream_with_context(generator()), mimetype="application/x-ndjson",
        )


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


# fmt: off
# Crawling / background tasks
...
# fmt: on

celery_app = Celery("quarchive")

processor: missive.Processor[missive.JSONMessage] = missive.Processor()


@processor.handle_for([lambda m: m.get_json()["event_type"] == "test"])
def test_message(message, ctx):
    log.info("test message recieved")
    ctx.ack(message)


adapted_processor = RabbitMQAdapter(missive.JSONMessage, processor, "quarchive-events")


@lru_cache(1)
def get_session_cls() -> Session:
    url: str = environ["QM_SQL_URL"]
    engine = create_engine(url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    log.info("using engine: %s", engine)
    return Session


REQUESTS_TIMEOUT = 30


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


@lru_cache(1)
def get_s3():
    session = boto3.Session(
        aws_access_key_id=environ["QM_AWS_ACCESS_KEY"],
        aws_secret_access_key=environ["QM_AWS_SECRET_ACCESS_KEY"],
        region_name=environ["QM_AWS_REGION_NAME"],
    )

    # This is a magic value to facilitate testing
    resource_kwargs = {}
    if environ["QM_AWS_S3_ENDPOINT_URL"] != "UNSET":
        resource_kwargs["endpoint_url"] = environ["QM_AWS_S3_ENDPOINT_URL"]

    resource = session.resource("s3", **resource_kwargs)
    resource.meta.client.meta.events.unregister("before-sign.s3", fix_s3_host)
    log.info("constructed s3 resource")
    return resource


@lru_cache(1)
def get_response_body_bucket():
    bucket = get_s3().Bucket(environ["QM_RESPONSE_BODY_BUCKET_NAME"])
    log.info("constructed response body bucket")
    return bucket


@celery_app.task
def celery_ok():
    log.info("ok")


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # FIXME: add periodic tasks here
    pass


def enqueue_crawls_for_uncrawled_urls():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(
                SQLAUrl.scheme,
                SQLAUrl.netloc,
                SQLAUrl.path,
                SQLAUrl.query,
                SQLAUrl.fragment,
            )
            .join(SQLABookmark)
            .outerjoin(CrawlRequest, SQLAUrl.url_uuid == CrawlRequest.url_uuid)
            .filter(CrawlRequest.crawl_uuid.is_(None))
        )
        uncrawled_urls = (urlunsplit(tup) for tup in rs)
    index = 0
    for index, uncrawled_url in enumerate(uncrawled_urls, start=1):
        log.info("enqueuing %s for crawl", uncrawled_url)
        ensure_crawled.delay(uncrawled_url)
    log.info("enqueued %d urls", index)


def enqueue_fulltext_indexing():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(CrawlResponse.crawl_uuid)
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .filter(FullText.crawl_uuid.is_(None))
        )
        for index, (crawl_uuid,) in enumerate(rs, start=1):
            log.info("enqueuing %s for crawl", crawl_uuid)
            ensure_fulltext.delay(crawl_uuid)
    log.info("enqueued %d items", index)


def get_meta_descriptions(root: lxml.html.HtmlElement) -> List[str]:
    meta_description_elements = root.xpath("//meta[@name='description']")
    if len(meta_description_elements) == 0:
        return []
    else:
        return [e.attrib.get("content", "") for e in meta_description_elements]


def extract_full_text_from_html(filelike: Union[BinaryIO, gzip.GzipFile]) -> str:
    # union required as gzip.GzipFile doesn't implement the full API required
    # by BinaryIO - we only need the shared subset
    document = lxml.html.parse(filelike)
    root = document.getroot()
    meta_descs = get_meta_descriptions(root)
    text_content: str = root.text_content()
    return " ".join(meta_descs + [text_content])


def upload_file(bucket, filelike: BinaryIO, filename: str) -> None:
    """Upload a fileobj into the bucket (compressed)"""
    with tempfile.TemporaryFile(mode="w+b") as temp_file:
        gzip_fileobj = gzip.GzipFile(mode="w+b", fileobj=temp_file)
        shutil.copyfileobj(filelike, gzip_fileobj)
        gzip_fileobj.close()
        temp_file.seek(0)
        bucket.upload_fileobj(temp_file, Key=filename)


def download_file(bucket, filename: str) -> gzip.GzipFile:
    """Download a fileobj from a bucket (decompressed)"""
    temp_file = tempfile.TemporaryFile(mode="w+b")
    bucket.download_fileobj(filename, temp_file)
    temp_file.seek(0)
    gzip_fileobj = gzip.GzipFile(mode="r+b", fileobj=temp_file)
    return gzip_fileobj


@lru_cache(1)
def known_content_types() -> FrozenSet[str]:
    mimetypes.init()
    return frozenset(mimetypes.types_map.values())


@celery_app.task
def ensure_crawled(url: str) -> None:
    """Crawl a url only if it has never been crawled before.

    For use from celery beat"""
    scheme, netloc, path, query, fragment = urlsplit(url)
    with contextlib.closing(get_session_cls()) as sesh:
        is_crawled: bool = sesh.query(
            sesh.query(CrawlRequest)
            .join(SQLAUrl)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .exists()
        ).scalar()
        if not is_crawled:
            crawl_uuid = uuid4()
            crawl_url(sesh, crawl_uuid, url)


def infer_content_type(fileobj: Union[BinaryIO, gzip.GzipFile]) -> str:
    """Use libmagic to infer the content type of a file from the first 2k."""
    content_type = magic.from_buffer(fileobj.read(2048), mime=True)
    fileobj.seek(0)
    return content_type


@celery_app.task
def ensure_fulltext(crawl_uuid: UUID) -> None:
    """Populate full text table for crawl"""
    with contextlib.closing(get_session_cls()) as sesh:
        content_type_header: Optional[str]
        body_uuid, content_type_header, sqla_url_obj, inserted = (
            sesh.query(
                CrawlResponse.body_uuid,
                CrawlResponse.headers["content-type"],
                SQLAUrl,
                FullText.inserted,
            )
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .join(CrawlRequest, CrawlResponse.crawl_uuid == CrawlRequest.crawl_uuid)
            .join(SQLAUrl, CrawlRequest.url_uuid == SQLAUrl.url_uuid)
            .filter(CrawlResponse.crawl_uuid == crawl_uuid)
            .one()
        )

        url = URL.from_sqla_url(sqla_url_obj)

        if inserted is not None:
            log.info(
                "%s (%s) already indexed - not indexing again", url.to_url(), crawl_uuid
            )
            return

        bucket = get_response_body_bucket()
        # Try to avoid downloading the content unless we need it
        fileobj = None

        # FIXME: Some error modes not handled here, see
        # https://github.com/calpaterson/quarchive/issues/11
        if content_type_header is not None:
            content_type, parameters = cgi.parse_header(content_type_header)
            # charset = parameters.get("charset")

            # If we were given something we don't recognise, infer the content type
            if content_type not in known_content_types():
                old_content_type = content_type
                fileobj = download_file(bucket, str(body_uuid))
                content_type = infer_content_type(fileobj)
                log.info(
                    "inferred %s for %s (instead of %s)",
                    content_type,
                    url.to_url(),
                    old_content_type,
                )
        else:
            # No Content-Type, so infer it
            fileobj = download_file(bucket, str(body_uuid))
            content_type = infer_content_type(fileobj)
            log.info("inferred %s for %s (none provided)", content_type, url.to_url())

        if content_type != "text/html":
            log.info(
                "%s (%s) has wrong content type: %s - skipping",
                url.to_url(),
                crawl_uuid,
                content_type,
            )
            return

        # If we didn't download it before, we should now
        if fileobj is None:
            fileobj = download_file(bucket, str(body_uuid))

        # FIXME: charset should be handed to extract_full_text_from_html
        text = extract_full_text_from_html(fileobj)

        fulltext_obj = FullText(
            url_uuid=sqla_url_obj.url_uuid,
            crawl_uuid=crawl_uuid,
            inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
            full_text=text,
            tsvector=func.to_tsvector(text),
        )
        sesh.add(fulltext_obj)
        sesh.commit()
        log.info("indexed %s (%s)", url.to_url(), crawl_uuid)


def crawl_url(session: Session, crawl_uuid: UUID, url: str) -> None:
    client = get_client()
    bucket = get_response_body_bucket()
    with contextlib.closing(get_session_cls()) as session:
        url_uuid = upsert_url(session, url)
        crawl_request = CrawlRequest(
            crawl_uuid=crawl_uuid,
            url_uuid=url_uuid,
            requested=datetime.utcnow().replace(tzinfo=timezone.utc),
            got_response=False,
        )
        session.add(crawl_request)

        try:
            response = client.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
        except requests.exceptions.RequestException as e:
            log.warning("unable to request %s - %s", url, e)
            session.commit()
            return
        log.info("crawled %s", url)

        crawl_request.got_response = True

        body_uuid = uuid4()
        # Typeshed type looks wrong, proposed a fix in
        # https://github.com/python/typeshed/pull/3610
        headers = cast(requests.structures.CaseInsensitiveDict, response.headers)
        session.add(
            CrawlResponse(
                crawl_uuid=crawl_uuid,
                body_uuid=body_uuid,
                headers=dict(headers.lower_items()),
                status_code=response.status_code,
            )
        )

        # Otherwise we'll get the raw stream (often gzipped) rather than the
        # raw payload (usually html bytes)
        response.raw.decode_content = True

        upload_file(bucket, response.raw, str(body_uuid))

        session.commit()


# fmt: off
# Search
...
# fmt: on

LEXER_REGEX = re.compile(r"[0-9A-z]+|['\"]")


class Term(metaclass=ABCMeta):
    @abstractmethod
    def render(self) -> str:
        pass


class Literal(Term):
    word: str

    def __init__(self, word: str) -> None:
        self.word = word

    def render(self):
        return "'" + self.word + "'"


class CompoundTerm(Term, metaclass=ABCMeta):
    @abstractmethod
    def append(self, term: Term) -> None:
        pass


class Conjunction(CompoundTerm):
    elems: MutableSequence[Term]

    def __init__(self) -> None:
        self.elems = []

    def append(self, term: Term) -> None:
        self.elems.append(term)

    def render(self) -> str:
        return " & ".join(e.render() for e in self.elems)


class Quote(CompoundTerm):
    quotes = {"'", '"'}

    literals: MutableSequence[Term]
    parent: CompoundTerm
    quote_char: str

    def __init__(self, parent: CompoundTerm) -> None:
        self.literals = []
        self.parent = parent

    def append(self, literal: Term) -> None:
        self.literals.append(literal)

    def render(self) -> str:
        return " <-> ".join(l.render() for l in self.literals)


def parse_search_str(search_str: str) -> str:
    """Parse a web search string into tquery format"""
    token_iterator = LEXER_REGEX.finditer(search_str)

    current_term: CompoundTerm = Conjunction()
    base_term = current_term
    for match_obj in token_iterator:
        token = match_obj.group(0)
        log.debug("token = '%s'", token)
        log.debug("base_term = '%s'", base_term.render())
        # FIXME: Need to handle apostrophe
        if token in Quote.quotes:
            if isinstance(current_term, Quote):
                current_term = current_term.parent
            else:
                quote = Quote(current_term)
                current_term.append(quote)
                current_term = quote
        else:
            term = Literal(token)
            current_term.append(term)

    return base_term.render()


# fmt: off
# Entry points
...
# fmt: on


def message_processor() -> None:
    logging.basicConfig(level=logging.INFO)
    adapted_processor.run()


def main() -> None:
    app = init_app()
    logging.basicConfig(level=logging.INFO)
    app.run()


@click.command()
@click.argument("user_uuid", type=click.UUID)
@click.argument("json_file", type=click.File("rb"))
@click.option(
    "--as-of",
    type=click.DateTime(),
    default=lambda: datetime.strftime(datetime.utcnow(), "%Y-%m-%d %H:%M:%S"),
)
def pinboard_import(user_uuid: UUID, json_file, as_of: datetime):
    as_of_dt = as_of.replace(tzinfo=timezone.utc)
    log.info("as of: %s", as_of_dt)

    def pinboard_bookmark_to_bookmark(mapping: Mapping[str, str]) -> Bookmark:
        creation_dt = isoparse(mapping["time"])
        if len(mapping.get("tags", "").strip()) == 0:
            tag_triples: TagTriples = frozenset()
        else:
            tag_triples = frozenset(
                (tag, creation_dt, False) for tag in mapping["tags"].split(" ")
            )
        return Bookmark(
            url=mapping["href"],
            title=mapping["description"],
            description=mapping["extended"],
            updated=as_of_dt,
            created=creation_dt,
            unread=True if mapping["toread"] == "yes" else False,
            deleted=False,
            tag_triples=tag_triples,
        )

    logging.basicConfig(level=logging.INFO)
    document = json.load(json_file)
    keys = set(itertools.chain(*[item.keys() for item in document]))
    log.info("keys = %s", keys)
    app = init_app()
    with app.app_context():
        generator = (pinboard_bookmark_to_bookmark(b) for b in document)
        changed = merge_bookmarks(db.session, user_uuid, generator)
        log.info("changed %d bookmarks", len(changed))
        db.session.commit()
