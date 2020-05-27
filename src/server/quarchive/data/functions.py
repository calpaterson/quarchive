import secrets
from logging import getLogger
from typing import Any, Iterable, Optional, Set, Tuple
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytz
from sqlalchemy import and_, cast as sa_cast, func, types as satypes
from sqlalchemy.dialects.postgresql import (
    ARRAY as PGARRAY,
    array as pg_array,
    insert as pg_insert,
)
from sqlalchemy.orm import Session

from quarchive.value_objects import (
    URL,
    Bookmark,
    User,
)

from .models import APIKey, BookmarkTag, SQLABookmark, SQLAUrl, SQLUser, Tag, UserEmail

log = getLogger(__name__)


def is_correct_api_key(session: Session, username: str, api_key: bytes) -> bool:
    api_key_from_db = get_api_key(session, username)
    return secrets.compare_digest(api_key, api_key_from_db)


def get_api_key(session, username: str) -> bytes:
    return (
        session.query(APIKey.api_key)
        .join(SQLUser)
        .filter(SQLUser.username == username)
        .scalar()
    )


def username_exists(session: Session, username: str) -> bool:
    return session.query(
        session.query(SQLUser).filter(SQLUser.username == username).exists()
    ).scalar()


def user_from_username(session, username: str) -> User:
    user_uuid, email, timezone = (
        session.query(SQLUser.user_uuid, UserEmail.email_address, SQLUser.timezone)
        .outerjoin(UserEmail)
        .filter(SQLUser.username == username)
        .one()
    )
    return User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )


def set_user_timezone(session, username: str, timezone: str):
    sql_user = session.query(SQLUser).filter(SQLUser.username == username).one()
    # Pass it through pytz to make sure the timezone does in fact exist
    timezone_name = pytz.timezone(timezone).zone
    sql_user.timezone = timezone_name
    log.debug("setting '%s' timezone to '%s'", username, timezone)


def user_from_user_uuid(session, user_uuid: UUID) -> User:
    username, email, timezone = (
        session.query(SQLUser.username, UserEmail.email_address, SQLUser.timezone)
        .outerjoin(UserEmail)
        .filter(SQLUser.user_uuid == user_uuid)
        .one()
    )
    return User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )


def create_user(
    session: Session,
    crypt_context: Any,
    username: str,
    password_plain: str,
    email: Optional[str] = None,
    timezone="Europe/London",
) -> UUID:
    user_uuid = uuid4()
    password_hashed = crypt_context.hash(password_plain)
    # FIXME: accept timezone as an argument (infer it somehow, from IP
    # address?)
    sql_user = SQLUser(
        user_uuid=user_uuid,
        username=username,
        password=password_hashed,
        timezone=timezone,
    )

    if email is not None:
        log.info("got an email for %s", username)
        sql_user.email_obj = UserEmail(email_address=email)

    sql_user.api_key_obj = APIKey(api_key=secrets.token_bytes(32))

    session.add(sql_user)
    return user_uuid


def get_bookmark_by_url(
    session: Session, user_uuid: UUID, url_string: str
) -> Optional[Bookmark]:
    url = URL.from_string(url_string)
    sqla_bookmark = (
        session.query(SQLABookmark)
        .filter(SQLABookmark.user_uuid == user_uuid, SQLABookmark.url_uuid == url.url_uuid)
        .first()
    )
    if sqla_bookmark is None:
        return None
    return bookmark_from_sqla(url_string, sqla_bookmark)


def get_bookmark_by_url_uuid(
    session: Session, user_uuid: UUID, url_uuid: UUID
) -> Optional[Bookmark]:
    sqla_bookmark = (
        session.query(SQLABookmark)
        .filter(SQLABookmark.user_uuid == user_uuid, SQLABookmark.url_uuid == url_uuid)
        .first()
    )
    if sqla_bookmark is None:
        return None
    url = sqla_bookmark.url_obj.to_url_string()
    return bookmark_from_sqla(url, sqla_bookmark)


def upsert_url(session: Session, url_string: str) -> UUID:
    url = URL.from_string(url_string)
    url_stmt = (
        pg_insert(SQLAUrl.__table__)
        .values(
            url_uuid=url.url_uuid,
            scheme=url.scheme,
            netloc=url.netloc,
            path=url.path,
            query=url.query,
            fragment=url.fragment,
        )
        .on_conflict_do_nothing(
            index_elements=["scheme", "netloc", "path", "query", "fragment"]
        )
    )
    session.execute(url_stmt)

    return url.url_uuid


def set_bookmark(session: Session, user_uuid: UUID, bookmark: Bookmark) -> UUID:
    url = bookmark.url
    if len(bookmark.tag_triples) > 0:
        tag_names, tag_updates, tag_deleted = zip(*bookmark.tag_triples)
    else:
        tag_names, tag_updates, tag_deleted = [()] * 3
    session.execute(
        func.insert_bookmark_v1(
            url.url_uuid,
            url.scheme,
            url.netloc,
            url.path,
            url.query,
            url.fragment,
            user_uuid,
            bookmark.title,
            bookmark.description,
            bookmark.created,
            bookmark.updated,
            bookmark.unread,
            bookmark.deleted,
            sa_cast(pg_array(tag_names), PGARRAY(satypes.String)),  # type:ignore
            sa_cast(
                pg_array(tag_updates),  # type:ignore
                PGARRAY(satypes.DateTime(timezone=True)),
            ),
            sa_cast(pg_array(tag_deleted), PGARRAY(satypes.Boolean)),  # type:ignore
        )
    )

    return url.url_uuid


def merge_bookmarks(
    session: Session, user_uuid: UUID, recieved_bookmarks: Iterable[Bookmark]
) -> Set[Bookmark]:
    changed_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(session, user_uuid, url_string=recieved.url.to_string())
        if existing is None:
            # If it doesn't exist in our db, we create it - but client already
            # knows
            set_bookmark(session, user_uuid, recieved)
            log.debug("added: %s", recieved)
        else:
            merged = existing.merge(recieved)
            if merged != existing:
                # If it exists but is old we have to update it
                log.debug(
                    "recieved bm merged, changing local: %s + %s = %s",
                    recieved,
                    existing,
                    merged,
                )
                set_bookmark(session, user_uuid, merged)
            else:
                log.debug("no change to %s", recieved)
            if merged != recieved:
                # If what we have is different from what were sent, we need to
                # tell the client
                changed_bookmarks.add(merged)
    return changed_bookmarks


def all_bookmarks(session, user_uuid: UUID) -> Iterable[Bookmark]:
    query = session.query(SQLABookmark).filter(SQLABookmark.user_uuid == user_uuid)
    for sqla_bookmark in query:
        url_obj = sqla_bookmark.url_obj
        url = urlunsplit(
            [
                url_obj.scheme,
                url_obj.netloc,
                url_obj.path,
                url_obj.query,
                url_obj.fragment,
            ]
        )
        yield bookmark_from_sqla(url, sqla_bookmark)


def bookmarks_with_tag(session, user: User, tag: str) -> Iterable[Bookmark]:
    query = (
        session.query(SQLAUrl, SQLABookmark)
        .join(SQLABookmark)
        .join(BookmarkTag)
        .join(Tag)
        .filter(SQLABookmark.user_uuid == user.user_uuid)
        .filter(~SQLABookmark.deleted)
        .filter(Tag.tag_name == tag)
        .order_by(SQLABookmark.created.desc())
    )
    for sqla_url, sqla_bookmark in query:
        yield bookmark_from_sqla(sqla_url.to_url_string(), sqla_bookmark)


def bookmarks_with_netloc(session, user: User, netloc: str) -> Iterable[Bookmark]:
    query = (
        session.query(SQLAUrl, SQLABookmark)
        .join(SQLABookmark)
        .filter(SQLABookmark.user_uuid == user.user_uuid)
        .filter(~SQLABookmark.deleted)
        .filter(SQLAUrl.netloc == netloc)
        .order_by(SQLABookmark.created.desc())
    )
    for sqla_url, sqla_bookmark in query:
        yield bookmark_from_sqla(sqla_url.to_url_string(), sqla_bookmark)


def tags_with_count(session, user: User) -> Iterable[Tuple[str, int]]:
    query = (
        session.query(Tag.tag_name, func.count(Tag.tag_name))
        .join(BookmarkTag)
        .join(
            SQLABookmark,
            and_(
                SQLABookmark.user_uuid == BookmarkTag.user_uuid,
                SQLABookmark.url_uuid == BookmarkTag.url_uuid,
            ),
        )
        .filter(BookmarkTag.user_uuid == user.user_uuid)
        .filter(~SQLABookmark.deleted)
        .group_by(Tag.tag_name)
        .order_by(func.count(Tag.tag_name).desc())
    )
    yield from query


def bookmark_from_sqla(url: str, sqla_obj: SQLABookmark) -> Bookmark:
    return Bookmark(
        url=URL.from_string(url),
        created=sqla_obj.created,
        description=sqla_obj.description,
        updated=sqla_obj.updated,
        unread=sqla_obj.unread,
        deleted=sqla_obj.deleted,
        title=sqla_obj.title,
        tag_triples=frozenset(
            (btag.tag_obj.tag_name, btag.updated, btag.deleted)
            for btag in sqla_obj.bookmark_tag_objs
        ),
    )
