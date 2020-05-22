import json
import re
from datetime import datetime, timezone
from functools import wraps
from logging import getLogger
from os import path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

import flask
import yaml
from sqlalchemy import func
from werkzeug import exceptions as exc

from quarchive.data.functions import (
    all_bookmarks,
    bookmarks_with_tag,
    bookmarks_with_netloc,
    create_user,
    get_api_key,
    get_bookmark_by_url_uuid,
    is_correct_api_key,
    merge_bookmarks,
    set_bookmark,
    tags_with_count,
    user_from_user_uuid,
    user_from_username,
    username_exists,
)
from quarchive.data.models import FullText, SQLABookmark, SQLAUrl, SQLUser
from quarchive.search import parse_search_str
from quarchive.value_objects import URL, Bookmark, TagTriples, User, bookmark_from_sqla

from .db_obj import db

log = getLogger(__name__)

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


@blueprint.route("/favicon.ico")
def favicon() -> flask.Response:
    return flask.current_app.send_static_file("icons/favicon.ico")


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


@blueprint.route("/user/<username>/netlocs/<netloc>")
@sign_in_required
def user_netloc(username: str, netloc: str) -> flask.Response:
    user = get_current_user()
    bookmarks = bookmarks_with_netloc(db.session, user, netloc)
    return flask.make_response(
        flask.render_template(
            "user_netloc.html",
            bookmarks=bookmarks,
            netloc=netloc,
            page_title="Bookmarks from '%s'" % netloc,
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
        recieved_bookmarks = (Bookmark.from_json(item) for item in body["bookmarks"])
    else:
        log.info("sync request using jsonlines")
        recieved_bookmarks = (
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
