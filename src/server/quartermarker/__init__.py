from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from werkzeug import exceptions as exc
from functools import wraps
import logging
from uuid import uuid4, UUID
from typing import Mapping, Set, Any, Optional, Callable
from os import environ
from urllib.parse import urlsplit, urlunsplit

from babel.dates import format_timedelta
from sqlalchemy import Column, ForeignKey, types as satypes
from sqlalchemy.orm import relationship, RelationshipProperty, Session
from sqlalchemy.dialects.postgresql import UUID as PGUUID, insert as pg_insert
from sqlalchemy.ext.declarative import declarative_base
from flask_sqlalchemy import SQLAlchemy
import flask
from flask_cors import CORS

log = logging.getLogger("quartermarker")

Base: Any = declarative_base()


class SQLAUrl(Base):
    __tablename__ = "urls"

    # Synthetic key for foreign references
    uuid = Column(PGUUID(as_uuid=True), nullable=False, index=True, unique=True)

    # The actual url
    scheme = Column(satypes.String, nullable=False, index=True, primary_key=True)
    netloc = Column(satypes.String, nullable=False, index=True, primary_key=True)
    path = Column(satypes.String, nullable=False, index=True, primary_key=True)
    query = Column(satypes.String, nullable=False, index=True, primary_key=True)
    fragment = Column(satypes.String, nullable=False, index=True, primary_key=True)


class SQLABookmark(Base):
    __tablename__ = "bookmarks"

    url = Column(PGUUID(as_uuid=True), ForeignKey("urls.uuid"), primary_key=True)
    updated = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    unread = Column(satypes.Boolean, nullable=False, index=True)
    deleted = Column(satypes.Boolean, nullable=False, index=True)
    title = Column(satypes.String, nullable=False, index=True)

    url_obj: RelationshipProperty = relationship(
        SQLAUrl, uselist=False, backref="bookmark_objs"
    )


@dataclass(frozen=True)
class Bookmark:
    url: str
    title: str
    # FIXME: Should have created timestamp
    updated: datetime
    unread: bool
    deleted: bool
    # FIXME: tags: Any

    def merge(self, other: "Bookmark") -> "Bookmark":
        # Take the one with the latest timestamp
        if self.updated != other.updated:
            return max((self, other), key=lambda b: b.updated)
        # If timestamps are equal, take the longest title
        else:
            return max((self, other), key=lambda b: b.title)
        # FIXME: all other fields should also be considered in case they differ
        # only in (eg unread)

    def to_json(self) -> Mapping:
        updated_millis = self.updated.timestamp() * 1000
        return {
            "url": self.url,
            "title": self.title,
            "timestamp": updated_millis,
            "unread": self.unread,
            "deleted": self.deleted,
        }

    @classmethod
    def from_json(cls, mapping: Mapping[str, Any]) -> "Bookmark":
        updated_dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            milliseconds=mapping["timestamp"]
        )
        return cls(
            url=mapping["url"],
            title=mapping["title"],
            updated=updated_dt,
            unread=mapping["unread"],
            deleted=mapping["deleted"],
        )


db = SQLAlchemy()
cors = CORS()
blueprint = flask.Blueprint("quartermarker", "quartermarker")


def bookmark_from_sqla(url: str, sqla_obj: SQLABookmark) -> Bookmark:
    return Bookmark(
        url=url,
        updated=sqla_obj.updated,
        unread=sqla_obj.unread,
        deleted=sqla_obj.deleted,
        title=sqla_obj.title,
    )


def get_bookmark_by_url(session: Session, url: str) -> Optional[Bookmark]:
    scheme, netloc, path, query, fragment = urlsplit(url)
    sqla_bookmark = (
        session.query(SQLABookmark)
        .join(SQLAUrl)
        .filter(
            SQLAUrl.scheme == scheme,
            SQLAUrl.netloc == netloc,
            SQLAUrl.path == path,
            SQLAUrl.query == query,
            SQLAUrl.fragment == fragment,
        )
        .first()
    )
    if sqla_bookmark is None:
        return None
    else:
        return bookmark_from_sqla(url, sqla_bookmark)


def set_bookmark(session: Session, bookmark: Bookmark) -> None:
    scheme, netloc, path, query, fragment = urlsplit(bookmark.url)
    proposed_uuid = uuid4()
    url_stmt = (
        pg_insert(SQLAUrl.__table__)
        .values(
            uuid=proposed_uuid,
            scheme=scheme,
            netloc=netloc,
            path=path,
            query=query,
            fragment=fragment,
        )
        .on_conflict_do_nothing(
            index_elements=["scheme", "netloc", "path", "query", "fragment"]
        )
        .returning(SQLAUrl.__table__.c.uuid)
    )
    upsert_result_set = session.execute(url_stmt).fetchone()

    url_uuid: UUID
    if upsert_result_set is None:
        # The update didn't happen, but we still need to know what the url uuid
        # is...
        (url_uuid,) = (
            session.query(SQLAUrl.uuid)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .one()
        )
    else:
        # If the update did happen, we know our proposed uuid was used
        url_uuid = proposed_uuid

    bookmark_insert_stmt = pg_insert(SQLABookmark.__table__).values(
        url=url_uuid,
        updated=bookmark.updated.replace(tzinfo=timezone.utc),
        unread=bookmark.unread,
        deleted=bookmark.deleted,
        title=bookmark.title,
    )
    bookmark_upsert_stmt = bookmark_insert_stmt.on_conflict_do_update(
        index_elements=["url"],
        set_=dict(
            updated=bookmark_insert_stmt.excluded.updated,
            unread=bookmark_insert_stmt.excluded.unread,
            deleted=bookmark_insert_stmt.excluded.deleted,
            title=bookmark_insert_stmt.excluded.title,
        ),
    )
    session.execute(bookmark_upsert_stmt)


def sign_in_required(
    handler: Callable[[], flask.Response]
) -> Callable[[], flask.Response]:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if "username" not in flask.session:
            return flask.redirect("/sign-in")
        else:
            return handler()

    return wrapper


@blueprint.route("/")
@sign_in_required
def index() -> flask.Response:
    page_size = flask.current_app.config["PAGE_SIZE"]
    page = int(flask.request.args.get("page", "1"))
    offset = (page - 1) * page_size
    sqla_objs = (
        db.session.query(SQLABookmark)
        .order_by(SQLABookmark.updated.desc())
        .offset(offset)
        .limit(page_size)
    )

    prev_page_exists = page > 1
    next_page_exists: bool = db.session.query(
        db.session.query(SQLABookmark)
        .order_by(SQLABookmark.updated.desc())
        .offset(offset + page_size)
        .exists()
    ).scalar()

    bookmarks = []
    for sqla_obj in sqla_objs:
        url_obj: SQLAUrl = sqla_obj.url_obj
        url = urlunsplit(
            [
                url_obj.scheme,
                url_obj.netloc,
                url_obj.path,
                url_obj.query,
                url_obj.fragment,
            ]
        )
        bookmarks.append(bookmark_from_sqla(url, sqla_obj))
    return flask.make_response(
        flask.render_template(
            "index.j2",
            bookmarks=bookmarks,
            page=page,
            prev_page_exists=prev_page_exists,
            next_page_exists=next_page_exists,
        )
    )


@blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(flask.render_template("sign-in.j2"))
    else:
        username = flask.request.form.get("username")
        password = flask.request.form.get("password")
        if password == flask.current_app.config["PASSWORD"]:
            flask.current_app.logger.info("successful sign in")
            flask.session["username"] = "username"

            # Make it last for 31 days
            flask.session.permanent = True

            # flask.redirect("/", code=303)
            response = flask.make_response("Redirecting...", 303)
            response.headers["Location"] = "/"
            return response
        else:
            flask.current_app.logger.info("unsuccessful sign in")
            raise exc.BadRequest()


@blueprint.route("/ok")
def ok() -> flask.Response:
    return flask.json.jsonify({"ok": True})


@blueprint.route("/sync", methods=["POST"])
def sync() -> flask.Response:
    body = flask.request.json
    recieved_bookmarks: Set[Bookmark] = set(
        Bookmark.from_json(item) for item in body["bookmarks"]
    )
    changed_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(db.session, url=recieved.url)
        if existing is None:
            # If it doesn't exist in our db, we create it - but client already
            # knows
            set_bookmark(db.session, recieved)
            log.info("added: %s", recieved)
        else:
            merged = existing.merge(recieved)
            if merged != existing:
                # If it exists but is old we have to update it
                log.info(
                    "recieved bm merged, changing local: %s + %s = %s",
                    recieved,
                    existing,
                    merged,
                )
                set_bookmark(db.session, merged)
            else:
                log.info("no change to %s", recieved)
            if merged != recieved:
                # If what we have is different from what were sent, we need to
                # tell the client
                changed_bookmarks.add(merged)

    db.session.commit()
    return flask.json.jsonify({"bookmarks": [b.to_json() for b in changed_bookmarks]})


def init_app(db_uri: str, password: str, secret_key: str) -> flask.Flask:
    app = flask.Flask("quartermarker")
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["PAGE_SIZE"] = 10
    app.config["PASSWORD"] = password
    db.init_app(app)
    cors.init_app(app)
    app.register_blueprint(blueprint)

    @app.template_filter("relativetime")
    def relativetime(dt: datetime):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        td = dt - now
        return format_timedelta(td, add_direction=True, locale="en_GB")

    return app


def main() -> None:
    app = init_app(
        environ["QM_SQL_URL"], environ["QM_PASSWORD"], environ["QM_SECRET_KEY"]
    )
    logging.basicConfig(level=logging.INFO)
    app.run()
