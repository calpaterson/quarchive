import re
from datetime import datetime, timezone
from functools import wraps
from logging import getLogger
from os import path, environ
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
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

import pytz
import flask
import yaml
from werkzeug import exceptions as exc

from quarchive.messaging import message_lib
from quarchive.archive import get_archive_links, Archive
from quarchive.messaging.publication import publish_message
from quarchive.cache import get_cache
from quarchive.data.functions import (
    BookmarkView,
    BookmarkViewQueryBuilder,
    create_user,
    get_api_key,
    get_bookmark_by_url_uuid,
    is_correct_password,
    set_bookmark,
    set_user_timezone,
    tags_with_count,
    user_from_user_uuid,
    user_from_username_if_exists,
    username_exists,
)
from quarchive.search import parse_search_str
from quarchive.value_objects import (
    Bookmark,
    DisallowedSchemeException,
    TagTriples,
    URL,
    User,
)
from .users import get_current_user, set_current_user
from .db_obj import db

log = getLogger(__name__)

web_blueprint = flask.Blueprint("quarchive", "quarchive")

# Flask's "views" are quite variable
V = TypeVar("V", bound=Callable)


def set_current_user_for_session(
    user: User, api_key: bytes, session: Optional[Any] = None
):
    """Sets the current user and creates a web session."""
    set_current_user(user)

    if session is None:
        session = flask.session
    session["user_uuid"] = user.user_uuid
    # Make it last for 31 days
    session.permanent = True

    flask.g.sync_credentials = "|".join([user.username, api_key.hex()])


@web_blueprint.after_request
def echo_session(response: flask.Response) -> flask.Response:
    # It's possible to use SESSION_REFRESH_EACH_REQUEST to echo the session
    # after each request.  However this is ONLY desirable when serving
    # endpoints from this blueprint (the one that serves the web ui) and not in
    # general - from the sync api or from the backup icon server blueprint
    flask.session.modified = True
    return response


@web_blueprint.after_request
def set_api_key_cookie_if_necessary(response: flask.Response) -> flask.Response:
    """If the user signed in in this session, set the sync_credentials cookie."""
    if hasattr(flask.g, "sync_credentials"):
        log.debug("setting sync_credentials cookie for %s", get_current_user())
        seconds_in_a_month = 31 * 24 * 60 * 60

        response.set_cookie(
            "sync_credentials",
            value=flask.g.sync_credentials,
            secure=True,
            max_age=seconds_in_a_month,
            httponly=True,
            samesite="Strict",
        )
    return response


@web_blueprint.before_request
def put_user_in_g() -> None:
    user_uuid: Optional[UUID] = flask.session.get("user_uuid")
    if user_uuid is not None:
        set_current_user(user_from_user_uuid(db.session, get_cache(), user_uuid))
        flask.current_app.logger.debug("currently signed in as: %s", get_current_user())
    else:
        flask.current_app.logger.debug("not signed in")


def sign_in_required(
    handler: Callable[..., flask.Response]
) -> Callable[..., flask.Response]:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        current_user = get_current_user()
        if current_user is None:
            # FIXME: This should use redirect_to
            return flask.redirect("/sign-in"), 302
        else:
            return handler(current_user, *args, **kwargs)

    return cast(Callable[..., flask.Response], wrapper)


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


@web_blueprint.route("/favicon.ico")
def favicon() -> flask.Response:
    # FIXME: Should set cache headers
    return flask.current_app.send_static_file("icons/favicon.ico")


@web_blueprint.route("/")
def index() -> flask.Response:
    response = flask.make_response("Redirecting...", 303)
    response.headers["Location"] = flask.url_for("quarchive.my_bookmarks")
    return response


@web_blueprint.route("/about")
def about() -> flask.Response:
    return flask.make_response(
        flask.render_template("about.html", page_title="About Quarchive")
    )


@web_blueprint.route("/getting-started")
def getting_started():
    return flask.make_response(
        flask.render_template("getting_started.html", page_title="Getting Started")
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


@web_blueprint.route("/create-bookmark")
@sign_in_required
def create_bookmark_form(current_user: User) -> flask.Response:
    template_kwargs: Dict[str, Any] = {"page_title": "Create bookmark"}
    template_kwargs.update(form_fields_from_querystring(flask.request.args))
    template_kwargs["tags_with_count"] = tags_with_count(db.session, current_user)

    return flask.make_response(
        flask.render_template("create_bookmark.html", **template_kwargs)
    )


@web_blueprint.route("/bookmarks")
@sign_in_required
def my_bookmarks(current_user: User) -> flask.Response:
    page = int(flask.request.args.get("page", "1"))
    qb = BookmarkViewQueryBuilder(db.session, current_user, page=page)

    if "q" in flask.request.args:
        search_str = flask.request.args["q"]
        tquery_str = parse_search_str(search_str)
        log.debug('search_str, tquery_str = ("%s", "%s")', search_str, tquery_str)

        qb = qb.text_search(tquery_str).order_by_search_rank()

        page_title = search_str
    else:
        qb = qb.order_by_created()
        page_title = "Quarchive"

    if page > 1:
        page_title += " (page %s)" % page

    prev_page_exists = qb.has_previous_page()
    next_page_exists = qb.has_next_page()

    return flask.make_response(
        flask.render_template(
            "bookmarks.html",
            h1="My bookmarks",
            page_title=page_title,
            bookmark_views=qb.execute(),
            page=page,
            prev_page_exists=prev_page_exists,
            next_page_exists=next_page_exists,
            search_query=flask.request.args.get("q", ""),
        )
    )


@web_blueprint.route("/bookmarks", methods=["POST"])
@sign_in_required
def create_bookmark(current_user: User) -> flask.Response:
    form = flask.request.form
    creation_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    tag_triples = tag_triples_from_form(form)

    url_str = form["url"]
    try:
        # As it's a user entering this url, help them along with getting a
        # sufficiently canonicalised url
        url = URL.from_string(url_str, coerce_canonicalisation=True)
    except DisallowedSchemeException:
        log.warning("user tried to create url: %s (disallowed scheme)", url_str)
        flask.abort(400, "invalid url (disallowed scheme)")

    bookmark = Bookmark(
        url=url,
        title=form["title"],
        description=form["description"],
        unread="unread" in form,
        deleted=False,
        updated=creation_time,
        created=creation_time,
        tag_triples=tag_triples,
    )
    url_uuid = set_bookmark(db.session, current_user.user_uuid, bookmark)
    db.session.commit()
    publish_message(
        message_lib.BookmarkCreated(
            user_uuid=current_user.user_uuid, url_uuid=url.url_uuid
        ),
        environ["QM_RABBITMQ_BG_WORKER_TOPIC"],
    )
    flask.flash("Bookmarked: %s" % bookmark.title)
    response = flask.make_response("Redirecting...", 303)
    response.headers["Location"] = flask.url_for(
        "quarchive.edit_bookmark_form", url_uuid=url_uuid
    )
    return response


@web_blueprint.route("/bookmarks/<uuid:url_uuid>", methods=["GET"])
@sign_in_required
@observe_redirect_to
def edit_bookmark_form(current_user: User, url_uuid: UUID) -> flask.Response:
    # access = check_access(current_user, get_access_tokens(flask.request), BookmarkEntitlement(user_uuid, url_uuid))
    # if access:
    #     ...
    bookmark = get_bookmark_by_url_uuid(db.session, current_user.user_uuid, url_uuid)
    if bookmark is None:
        # FIXME: er, write a test for this
        flask.abort(404, description="bookmark not found")

    # Step one, load the template kwargs from the bookmark
    template_kwargs: Dict[str, Any] = dict(
        url=bookmark.url.to_string(),
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

    template_kwargs["tags_with_count"] = tags_with_count(db.session, current_user)
    template_kwargs["deleted"] = bookmark.deleted

    return flask.make_response(
        flask.render_template("edit_bookmark.html", **template_kwargs)
    )


@web_blueprint.route("/bookmarks/<uuid:url_uuid>/archives", methods=["GET"])
@sign_in_required
def bookmark_archives(current_user: User, url_uuid: UUID) -> flask.Response:
    bookmark = get_bookmark_by_url_uuid(db.session, current_user.user_uuid, url_uuid)
    if bookmark is None:
        flask.abort(404, description="bookmark not found")

    archive_links = get_archive_links(bookmark.url, circa=bookmark.created)

    return flask.make_response(
        flask.render_template(
            "archives.html",
            page_title=f'Archives of "{bookmark.title}"',
            bookmark=bookmark,
            archive_links=archive_links,
            Archive=Archive,
        )
    )


@web_blueprint.route("/bookmarks/<uuid:url_uuid>/links", methods=["GET"])
@sign_in_required
def links(current_user: User, url_uuid: UUID) -> flask.Response:
    bookmark = get_bookmark_by_url_uuid(db.session, current_user.user_uuid, url_uuid)
    if bookmark is None:
        # FIXME: er, write a test for this
        flask.abort(404, description="bookmark not found")

    page = int(flask.request.args.get("page", "1"))
    user = get_current_user()
    qb = (
        BookmarkViewQueryBuilder(db.session, current_user, page=page)
        .links(url_uuid)
        .order_by_created()
    )
    title = f"Links from '{bookmark.title}'"
    return flask.make_response(
        flask.render_template(
            "bookmarks.html",
            h1=title,
            page_title=title,
            bookmark_views=qb.execute(),
            page=page,
            prev_page_exists=qb.has_previous_page(),
            next_page_exists=qb.has_next_page(),
            search_query=False,
        )
    )


@web_blueprint.route("/bookmarks/<uuid:url_uuid>/backlinks", methods=["GET"])
@sign_in_required
def backlinks(current_user: User, url_uuid: UUID) -> flask.Response:
    bookmark = get_bookmark_by_url_uuid(db.session, current_user.user_uuid, url_uuid)
    if bookmark is None:
        # FIXME: er, write a test for this
        flask.abort(404, description="bookmark not found")

    page = int(flask.request.args.get("page", "1"))
    user = get_current_user()
    qb = (
        BookmarkViewQueryBuilder(db.session, current_user, page=page)
        .backlinks(url_uuid)
        .order_by_created()
    )
    title = f"Links to '{bookmark.title}'"
    return flask.make_response(
        flask.render_template(
            "bookmarks.html",
            h1=title,
            page_title=title,
            bookmark_views=qb.execute(),
            page=page,
            prev_page_exists=qb.has_previous_page(),
            next_page_exists=qb.has_next_page(),
            search_query=False,
        )
    )


@web_blueprint.route("/bookmarks/<uuid:url_uuid>", methods=["POST"])
@sign_in_required
@observe_redirect_to
def edit_bookmark(current_user: User, url_uuid: UUID) -> flask.Response:
    form = flask.request.form
    existing_bookmark = get_bookmark_by_url_uuid(
        db.session, current_user.user_uuid, url_uuid
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

    set_bookmark(db.session, current_user.user_uuid, merged_bookmark)
    db.session.commit()
    flask.flash("Edited: %s" % merged_bookmark.title)
    return flask.make_response("ok")


@web_blueprint.route("/register", methods=["GET", "POST"])
def register() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("register.html", page_title="Register")
        )
    else:
        username = flask.request.form["username"]
        password_plain = flask.request.form["password"]
        email: Optional[str] = flask.request.form["email"] or None
        cache = get_cache()

        if username_exists(db.session, username):
            log.error("username already registered: %s", username)
            flask.abort(400, description="username already exists")

        username_regex = r"^[A-z0-9_\-]+$"
        if not re.compile(username_regex).match(username):
            log.error("invalid username: %s", username)
            flask.abort(
                400, description="invalid username - must match %s" % username_regex
            )

        user, api_key = create_user(
            db.session,
            cache,
            flask.current_app.config["CRYPT_CONTEXT"],
            username,
            password_plain,
            email,
        )

        db.session.commit()
        response = flask.make_response("Redirecting...", 303)
        response.headers["Location"] = flask.url_for("quarchive.my_bookmarks")
        log.info("created user: %s", user.username)

        set_current_user_for_session(user, api_key)

        return response


@web_blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("sign-in.html", page_title="Sign in")
        )
    else:
        crypt_context = flask.current_app.config["CRYPT_CONTEXT"]

        username = flask.request.form["username"]
        cache = get_cache()
        user = user_from_username_if_exists(db.session, cache, username)

        if user is None:
            flask.current_app.logger.info(
                "unsuccessful sign in - no such user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")

        password = flask.request.form["password"]
        if is_correct_password(db.session, crypt_context, user, password):
            flask.current_app.logger.info("successful sign in")

            # In this context the user exists to the api key must too
            api_key = cast(bytes, get_api_key(db.session, get_cache(), user.username))

            set_current_user_for_session(user, api_key)
            flask.flash("Signed in")

            response = flask.make_response("Redirecting...", 303)
            response.headers["Location"] = "/"
            return response
        else:
            flask.current_app.logger.info(
                "unsuccessful sign in - wrong password for user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")


@web_blueprint.route("/sign-out", methods=["GET"])
@sign_in_required
def sign_out(current_user: User) -> flask.Response:
    flask.session.clear()
    flask.flash("Signed out")
    return flask.make_response(flask.render_template("base.html"))


@web_blueprint.route("/users/<username>", methods=["GET"])
def user_page(username: str) -> flask.Response:
    cache = get_cache()
    user = user_from_username_if_exists(db.session, cache, username)
    api_key: Optional[bytes]
    if user is None:
        flask.abort(404, "user not found")
    elif user == get_current_user():
        api_key = get_api_key(db.session, cache, user.username)
    else:
        api_key = None
    return flask.make_response(
        flask.render_template(
            "user.html",
            user=user,
            api_key=api_key,
            timezones=pytz.common_timezones,
            current_timezone=user.timezone.zone,
        )
    )


@web_blueprint.route("/users/<username>", methods=["POST"])
def user_page_post(username: str) -> Tuple[flask.Response, int]:
    user = user_from_username_if_exists(db.session, get_cache(), username)
    if user is None:
        flask.abort(404, "user not found")
    elif user != get_current_user():
        flask.abort(403, "not allowed to edit the profiles of others")
    else:
        set_user_timezone(db.session, get_cache(), user, flask.request.form["timezone"])
        db.session.commit()
        put_user_in_g()
        flask.flash("User updated successfully")
        response = flask.make_response("Redirecting...")
        response.headers["Location"] = flask.url_for(
            "quarchive.user_page", username=username
        )
        return response, 303


@web_blueprint.route("/users/<username>/tags/<tag>")
@sign_in_required
def user_tag(current_user: User, username: str, tag: str) -> flask.Response:
    bookmark_views: Iterable[BookmarkView] = BookmarkViewQueryBuilder(
        db.session, current_user
    ).with_tag(tag).execute()
    return flask.make_response(
        flask.render_template(
            "user_tag.html",
            bookmark_views=bookmark_views,
            tag=tag,
            page_title="Tagged as '%s'" % tag,
        )
    )


@web_blueprint.route("/users/<username>/netlocs/<netloc>")
@sign_in_required
def user_netloc(current_user: User, username: str, netloc: str) -> flask.Response:
    bookmark_views: Iterable[BookmarkView] = BookmarkViewQueryBuilder(
        db.session, current_user
    ).with_netloc(netloc).execute()
    return flask.make_response(
        flask.render_template(
            "user_netloc.html",
            bookmark_views=bookmark_views,
            netloc=netloc,
            page_title="Bookmarks from '%s'" % netloc,
        )
    )


@web_blueprint.route("/users/<username>/tags")
@sign_in_required
def user_tags(current_user: User, username: str) -> flask.Response:
    tag_counts = tags_with_count(db.session, current_user)
    tt1 = list(tag_counts)
    return flask.make_response(
        flask.render_template("user_tags.html", tag_counts=tt1, page_title="My tags")
    )


@web_blueprint.route("/faq")
def faq() -> flask.Response:
    here = path.dirname(path.realpath(__file__))
    with open(path.join(here, "faq.yaml")) as faq_f:
        faq = yaml.safe_load(faq_f)

    return flask.make_response(flask.render_template("faq.html", faq=faq))


@web_blueprint.route("/ok")
def ok() -> flask.Response:
    return flask.json.jsonify({"ok": True})


@web_blueprint.context_processor
def inject_gcu():
    return dict(get_current_user=get_current_user)
