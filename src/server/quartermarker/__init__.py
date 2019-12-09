from dataclasses import dataclass, asdict as dataclass_as_dict
from datetime import datetime, timezone, timedelta
import logging
from uuid import uuid4
from typing import Mapping, Set, Any, Optional
from os import environ
from urllib.parse import urlsplit

from sqlalchemy import Column, ForeignKey, types as satypes
from sqlalchemy.orm import relationship, RelationshipProperty
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
    # FIXME: 'timestamp' should be 'updated'
    timestamp: int
    unread: bool
    deleted: bool
    # FIXME: tags: Any

    def merge(self, other):
        # Take the one with the latest timestamp
        if self.timestamp != other.timestamp:
            return max((self, other), key=lambda b: b.timestamp)
        # If timestamps are equal, take the longest title
        else:
            return max((self, other), key=lambda b: b.title)
        # FIXME: all other fields should also be considered in case they differ
        # only in (eg unread)

    def to_json(self) -> Mapping:
        return dataclass_as_dict(self)

    @classmethod
    def from_json(cls, mapping: Mapping) -> "Bookmark":
        return cls(**mapping)


db = SQLAlchemy()
cors = CORS()

blueprint = flask.Blueprint("quartermarker", "quartermarker")


def get_bookmark_by_url(session: Any, url: str) -> Optional[Bookmark]:
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
        return Bookmark(
            url=url,
            timestamp=int(sqla_bookmark.updated.timestamp() * 1000),
            unread=sqla_bookmark.unread,
            deleted=sqla_bookmark.deleted,
            title=sqla_bookmark.title,
        )


def set_bookmark(session: Any, bookmark: Bookmark) -> None:
    scheme, netloc, path, query, fragment = urlsplit(bookmark.url)
    url_uuid = (
        pg_insert(SQLAUrl.__table__)
        .values(
            uuid=uuid4(),
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
    (url_uuid,) = session.execute(url_uuid).fetchone()

    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        milliseconds=bookmark.timestamp
    )
    bookmark_insert_stmt = pg_insert(SQLABookmark.__table__).values(
        url=url_uuid,
        updated=dt,
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
    session.commit()


@blueprint.route("/ok")
def ok():
    return flask.json.jsonify({"ok": True})


@blueprint.route("/sync", methods=["POST"])
def sync():
    body = flask.request.json
    recieved_bookmarks: Set[Bookmark] = set(
        Bookmark.from_json(item) for item in body["bookmarks"]
    )
    changed_bookmarks: Set[Bookmark] = set()
    new_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(db.session, url=recieved.url)
        if existing is not None:
            merged = existing.merge(recieved)
            if merged != existing:
                log.info(
                    "recieved bm merged, changing local: %s + %s = %s",
                    recieved,
                    existing,
                    merged,
                )
            else:
                log.info("no change to %s", recieved)
            if recieved != merged:
                log.info("recieved bm changed by merge: %s -> %s", recieved, merged)
                changed_bookmarks.add(merged)
                # FIXME: And set!!!
        else:
            new_bookmarks.add(recieved)
            set_bookmark(db.session, recieved)
            log.info("added: %s", recieved)
    return flask.json.jsonify({"bookmarks": [b.to_json() for b in changed_bookmarks]})


def init_app(db_uri: str):
    app = flask.Flask("quartermarker")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    cors.init_app(app)
    app.register_blueprint(blueprint)
    return app


def main():
    app = init_app(environ["QM_SQL_URL"])
    logging.basicConfig(level=logging.INFO)
    app.run()
