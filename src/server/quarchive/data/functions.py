from os import environ
import secrets
from logging import getLogger
from typing import Any, Iterable, Optional, Set, Tuple, Dict
from urllib.parse import urlunsplit
from uuid import UUID, uuid4
from datetime import datetime, timezone
from dataclasses import dataclass

import pytz
from pyappcache.cache import Cache
from pyappcache.keys import Key
from sqlalchemy import and_, cast as sa_cast, func, types as satypes, create_engine
from sqlalchemy.sql.expression import case
from sqlalchemy.dialects.postgresql import (
    ARRAY as PGARRAY,
    array as pg_array,
    insert as pg_insert,
)
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from quarchive.cache import get_cache
from quarchive.value_objects import (
    URL,
    Bookmark,
    User,
)

from .models import (
    APIKey,
    BookmarkTag,
    SQLABookmark,
    SQLAUrl,
    SQLUser,
    Tag,
    UserEmail,
    CrawlRequest,
    CrawlResponse,
    FullText,
    IndexingError,
)

log = getLogger(__name__)


def get_session_cls() -> Session:
    url: str = environ["QM_SQL_URL"]
    engine = create_engine(url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    log.info("using engine: %s", engine)
    return Session


class UserUUIDToUserKey(Key[User]):
    def __init__(self, user_uuid: UUID):
        self._user_uuid = user_uuid

    def as_segments(self):
        return [str(self._user_uuid)]


class UsernameToUserKey(Key[User]):
    def __init__(self, username: str):
        self._username = username

    def as_segments(self):
        return [self._username]


class UsernameToApiKey(Key[bytes]):
    def __init__(self, username: str):
        self._username = username

    def as_segments(self):
        return [self._username, "api_key"]


def put_user_in_cache(cache: Cache, user: User):
    cache.set(UserUUIDToUserKey(user.user_uuid), user)
    cache.set(UsernameToUserKey(user.username), user)


def is_correct_api_key(
    session: Session, cache: Cache, username: str, api_key: bytes
) -> bool:
    api_key_from_db = get_api_key(session, cache, username)
    return secrets.compare_digest(api_key, api_key_from_db)


def get_api_key(session, cache: Cache, username: str) -> bytes:
    cache_key = UsernameToApiKey(username)
    api_key = cache.get(cache_key)
    if api_key is not None:
        return api_key

    api_key = (
        session.query(APIKey.api_key)
        .join(SQLUser)
        .filter(SQLUser.username == username)
        .scalar()
    )
    cache.set(cache_key, api_key)
    return api_key


def username_exists(session: Session, username: str) -> bool:
    return session.query(
        session.query(SQLUser).filter(SQLUser.username == username).exists()
    ).scalar()


def set_user_timezone(session, cache: Cache, username: str, timezone_name: str) -> None:
    # Pass it through pytz to make sure the timezone does in fact exist
    timezone = pytz.timezone(timezone_name)
    timezone_name = timezone.zone

    # update the cache
    user = user_from_username(session, cache, username)
    user.timezone = timezone
    put_user_in_cache(cache, user)

    sql_user = session.query(SQLUser).filter(SQLUser.username == username).one()
    sql_user.timezone = timezone_name
    log.debug("set '%s' timezone to '%s'", username, timezone)


def user_from_username(session, cache: Cache, username: str) -> User:
    key = UsernameToUserKey(username)
    user = cache.get(key)
    if user is not None:
        return user

    user_uuid, email, timezone = (
        session.query(SQLUser.user_uuid, UserEmail.email_address, SQLUser.timezone)
        .outerjoin(UserEmail)
        .filter(SQLUser.username == username)
        .one()
    )
    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )
    put_user_in_cache(cache, user)
    return user


def user_from_user_uuid(session, cache: Cache, user_uuid: UUID) -> User:
    key = UserUUIDToUserKey(user_uuid)
    user = cache.get(key)
    if user is not None:
        return user

    username, email, timezone = (
        session.query(SQLUser.username, UserEmail.email_address, SQLUser.timezone)
        .outerjoin(UserEmail)
        .filter(SQLUser.user_uuid == user_uuid)
        .one()
    )
    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )
    put_user_in_cache(cache, user)
    return user


def create_user(
    session: Session,
    cache: Cache,
    crypt_context: Any,
    username: str,
    password_plain: str,
    email: Optional[str] = None,
    timezone="Europe/London",
) -> UUID:
    user_uuid = uuid4()

    key = UserUUIDToUserKey(user_uuid)

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
    session.flush()

    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )
    put_user_in_cache(cache, user)

    return user_uuid


def get_bookmark_by_url(
    session: Session, user_uuid: UUID, url_string: str
) -> Optional[Bookmark]:
    url = URL.from_string(url_string)
    sqla_bookmark = (
        session.query(SQLABookmark)
        .filter(
            SQLABookmark.user_uuid == user_uuid, SQLABookmark.url_uuid == url.url_uuid
        )
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


def upsert_url(session: Session, url: URL) -> UUID:
    """Put a url into the database if it isn't already present"""
    # This could clearly be faster if it used the url uuid better
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


def get_url_by_url_uuid(session: Session, url_uuid: UUID) -> Optional[URL]:
    """Get a URL object by url uuid"""
    sql_url = session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url_uuid).first()
    return sql_url.to_url()


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


@dataclass
class MergeResult:
    changed: Set[Bookmark]
    added: Set[Bookmark]


def merge_bookmarks(
    session: Session, user_uuid: UUID, recieved_bookmarks: Iterable[Bookmark]
) -> MergeResult:
    added_bookmarks: Set[Bookmark] = set()
    changed_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(
            session, user_uuid, url_string=recieved.url.to_string()
        )
        if existing is None:
            # If it doesn't exist in our db, we create it - but client already
            # knows
            set_bookmark(session, user_uuid, recieved)
            log.debug("added: %s", recieved)
            added_bookmarks.add(recieved)
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
    return MergeResult(changed=changed_bookmarks, added=added_bookmarks)


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


def get_all_urls_as_5_tuples(
    session: Session,
) -> Iterable[Tuple[UUID, Tuple[str, str, str, str, str]]]:
    query = session.query(
        SQLAUrl.url_uuid,
        SQLAUrl.scheme,
        SQLAUrl.netloc,
        SQLAUrl.path,
        SQLAUrl.query,
        SQLAUrl.fragment,
    )
    for uuid, s, n, p, q, f in query:
        yield (uuid, (s, n, p, q, f))


def delete_bookmark(session, user_uuid: UUID, url_uuid: UUID):
    """Delete a bookmark by user_uuid and url_uuid.  For test purposes only"""
    log.warning("deleting bookmark: %s %s", user_uuid, url_uuid)
    query = session.query(SQLABookmark).filter(
        SQLABookmark.url_uuid == url_uuid, SQLABookmark.user_uuid == user_uuid
    )
    query.delete(synchronize_session="fetch")


def delete_url(session, url_uuid: UUID):
    """Delete a url by url_uuid.  For test purposes only"""
    log.warning("deleting url: %s", url_uuid)
    query = session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url_uuid)
    query.delete(synchronize_session="fetch")


def is_crawled(session: Session, url: URL):
    """Return true if we've already attempted to crawl this url"""
    return_value: bool = session.query(
        session.query(CrawlRequest)
        .filter(CrawlRequest.url_uuid == url.url_uuid)
        .exists()
    ).scalar()
    return return_value


def get_uncrawled_urls(session: Session) -> Iterable[URL]:
    """Return an all uncrawled urls"""
    query = (
        session.query(SQLAUrl)
        .outerjoin(CrawlRequest)
        .filter(CrawlRequest.crawl_uuid.is_(None))
    )
    for sqla_url in query:
        yield sqla_url.to_url()


def get_unindexed_urls(session: Session) -> Iterable[Tuple[URL, UUID]]:
    """Returns unindexed urls and their most recent crawl_uuid"""
    most_recent_crawls = (
        session.query(
            CrawlRequest.crawl_uuid, SQLAUrl.url_uuid, func.max(CrawlRequest.requested)
        )
        .join(SQLAUrl, CrawlRequest.url_uuid == SQLAUrl.url_uuid)
        .filter(CrawlRequest.got_response)
        .join(CrawlResponse, CrawlRequest.crawl_uuid == CrawlResponse.crawl_uuid)
        .group_by(CrawlRequest.crawl_uuid, SQLAUrl.url_uuid)
        .subquery()
    )
    which_are_missing_from_fulltext = (
        session.query(most_recent_crawls.c.crawl_uuid, SQLAUrl)
        .outerjoin(FullText, most_recent_crawls.c.crawl_uuid == FullText.crawl_uuid)
        .join(SQLAUrl, most_recent_crawls.c.url_uuid == SQLAUrl.url_uuid)
        .filter(FullText.crawl_uuid.is_(None))
    )
    for crawl_uuid, sqla_url in which_are_missing_from_fulltext:
        print(crawl_uuid, sqla_url.to_url())
        yield sqla_url.to_url(), crawl_uuid


def create_crawl_request(session: Session, crawl_uuid: UUID, url):
    """Record a request that was made"""
    crawl_request = CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=url.url_uuid,
        requested=datetime.utcnow().replace(tzinfo=timezone.utc),
        got_response=False,
    )
    session.add(crawl_request)


def mark_crawl_request_with_response(session: Session, crawl_uuid: UUID):
    """Mark the crawl request as having gotten a response"""
    crawl_request = session.query(CrawlRequest).get(crawl_uuid)
    crawl_request.got_response = True


def add_crawl_response(
    session: Session,
    crawl_uuid: UUID,
    body_uuid: UUID,
    headers: Dict[str, Any],
    status_code: int,
):
    """Save a crawl response"""
    session.add(
        CrawlResponse(
            crawl_uuid=crawl_uuid,
            body_uuid=body_uuid,
            headers=headers,
            status_code=status_code,
        )
    )


@dataclass(frozen=True)
class CrawlMetadata:
    body_uuid: UUID
    content_type: Optional[str]
    fulltext_failed: bool
    fulltext_inserted: Optional[datetime]
    url: URL


def get_crawl_metadata(session: Session, crawl_uuid: UUID) -> CrawlMetadata:
    """Return some crawl metadata (for indexing purposes)"""
    body_uuid, content_type_header, sqla_url_obj, inserted, previous_failure = (
        session.query(
            CrawlResponse.body_uuid,
            CrawlResponse.headers["content-type"],
            SQLAUrl,
            FullText.inserted,
            case([(IndexingError.crawl_uuid.is_(None), False)], else_=True),
        )
        .join(CrawlRequest, CrawlResponse.crawl_uuid == CrawlRequest.crawl_uuid)
        .join(SQLAUrl, CrawlRequest.url_uuid == SQLAUrl.url_uuid)
        .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
        .outerjoin(IndexingError, CrawlResponse.crawl_uuid == IndexingError.crawl_uuid)
        .filter(CrawlResponse.crawl_uuid == crawl_uuid)
        .one()
    )
    return CrawlMetadata(
        body_uuid=body_uuid,
        content_type=content_type_header,
        fulltext_failed=previous_failure,
        fulltext_inserted=inserted,
        url=sqla_url_obj.to_url(),
    )


def add_fulltext(session: Session, url: URL, crawl_uuid: UUID, text: str) -> None:
    fulltext_obj = FullText(
        url_uuid=url.url_uuid,
        crawl_uuid=crawl_uuid,
        inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
        full_text=text,
        tsvector=func.to_tsvector(text),
    )
    session.add(fulltext_obj)


def record_index_error(session: Session, crawl_uuid: UUID, message: str) -> None:
    session.add(IndexingError(crawl_uuid=crawl_uuid, description=message))
