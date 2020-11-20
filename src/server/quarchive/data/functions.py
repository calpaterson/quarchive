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
from sqlalchemy.orm import sessionmaker, Session

from quarchive.html_metadata import HTMLMetadata
from quarchive.value_objects import (
    URL,
    Bookmark,
    User,
)

from .models import (
    APIKey,
    BookmarkTag,
    CrawlRequest,
    CrawlResponse,
    DomainIcon,
    FullText,
    Icon,
    IndexingError,
    SQLABookmark,
    SQLAUrl,
    SQLUser,
    Tag,
    URLIcon,
    UserEmail,
)

log = getLogger(__name__)


def get_session_cls() -> sessionmaker:
    """Return a Session class (in fact, a sessionmaker instance) - used to get
    database sessions."""
    url: str = environ["QM_SQL_URL"]
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
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


@dataclass
class BookmarkView:
    """A bookmark with all the associated metadata to allow it to be displayed
     on the web: eg icon_uuid, (eventually) links, discussions, etc."""

    bookmark: Bookmark
    icon_uuid: Optional[UUID]


def put_user_in_cache(cache: Cache, user: User):
    cache.set(UserUUIDToUserKey(user.user_uuid), user)
    cache.set(UsernameToUserKey(user.username), user)


def is_correct_api_key(
    session: Session, cache: Cache, username: str, api_key: bytes
) -> bool:
    api_key_from_db = get_api_key(session, cache, username)
    if api_key_from_db is None:
        return False
    return secrets.compare_digest(api_key, api_key_from_db)


def get_api_key(session, cache: Cache, username: str) -> Optional[bytes]:
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


def set_user_timezone(session, cache: Cache, user: User, timezone_name: str) -> None:
    # Pass it through pytz to make sure the timezone does in fact exist
    timezone = pytz.timezone(timezone_name)
    timezone_name = timezone.zone

    # update the cache
    user.timezone = timezone
    put_user_in_cache(cache, user)

    sql_user = session.query(SQLUser).filter(SQLUser.user_uuid == user.user_uuid).one()
    sql_user.timezone = timezone_name
    log.debug("set '%s' timezone to '%s'", user.username, timezone)


def user_from_username_if_exists(
    session, cache: Cache, username: str
) -> Optional[User]:
    key = UsernameToUserKey(username)
    user = cache.get(key)
    if user is not None:
        return user

    user_triple = (
        session.query(SQLUser.user_uuid, UserEmail.email_address, SQLUser.timezone)
        .outerjoin(UserEmail)
        .filter(SQLUser.username == username)
        .first()
    )

    # User doesn't exist
    if user_triple is None:
        return None

    user_uuid, email, timezone = user_triple

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
) -> Tuple[User, bytes]:
    """Creates a new user, returns User object and api_key"""
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

    api_key = secrets.token_bytes(32)
    sql_user.api_key_obj = APIKey(api_key=api_key)

    session.add(sql_user)
    session.flush()

    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
    )
    put_user_in_cache(cache, user)

    return user, api_key


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
    return bookmark_from_sqla(url, sqla_bookmark)


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
    url = sqla_bookmark.url_obj.to_url()
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
    sqla_url: Optional[SQLAUrl] = session.query(SQLAUrl).filter(
        SQLAUrl.url_uuid == url_uuid
    ).first()
    if sqla_url is not None:
        return sqla_url.to_url()
    return None


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
    query = (
        session.query(SQLABookmark)
        .join(SQLAUrl)
        .filter(SQLABookmark.user_uuid == user_uuid)
    )
    for sqla_bookmark in query:
        url_obj = sqla_bookmark.url_obj
        yield bookmark_from_sqla(url_obj.to_url(), sqla_bookmark)


def bookmarks_with_tag(session, user: User, tag: str) -> Iterable[BookmarkView]:
    query: Iterable[Tuple[SQLAUrl, SQLABookmark, Optional[UUID]]] = (
        session.query(
            SQLAUrl,
            SQLABookmark,
            func.coalesce(URLIcon.icon_uuid, DomainIcon.icon_uuid),
        )
        .join(SQLABookmark)
        .join(BookmarkTag)
        .join(Tag)
        .outerjoin(URLIcon)
        .outerjoin(
            DomainIcon,
            and_(
                DomainIcon.scheme == SQLAUrl.scheme, DomainIcon.netloc == SQLAUrl.netloc
            ),
        )
        .filter(SQLABookmark.user_uuid == user.user_uuid)
        .filter(~SQLABookmark.deleted)
        .filter(Tag.tag_name == tag)
        .order_by(SQLABookmark.created.desc())
    )
    for sqla_url, sqla_bookmark, icon_uuid in query:
        yield BookmarkView(
            bookmark=bookmark_from_sqla(sqla_url.to_url(), sqla_bookmark),
            icon_uuid=icon_uuid,
        )


def bookmarks_with_netloc(session, user: User, netloc: str) -> Iterable[BookmarkView]:
    # FIXME: seem to be no tests for this?
    query = (
        session.query(
            SQLAUrl,
            SQLABookmark,
            func.coalesce(URLIcon.icon_uuid, DomainIcon.icon_uuid),
        )
        .join(SQLABookmark)
        .outerjoin(URLIcon)
        .outerjoin(
            DomainIcon,
            and_(
                DomainIcon.scheme == SQLAUrl.scheme, DomainIcon.netloc == SQLAUrl.netloc
            ),
        )
        .filter(SQLABookmark.user_uuid == user.user_uuid)
        .filter(~SQLABookmark.deleted)
        .filter(SQLAUrl.netloc == netloc)
        .order_by(SQLABookmark.created.desc())
    )
    for sqla_url, sqla_bookmark, icon_uuid in query:
        yield BookmarkView(
            bookmark=bookmark_from_sqla(sqla_url.to_url(), sqla_bookmark),
            icon_uuid=icon_uuid,
        )


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


def bookmark_from_sqla(url: URL, sqla_obj: SQLABookmark) -> Bookmark:
    return Bookmark(
        url=url,
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


def upsert_metadata(session: Session, crawl_uuid: UUID, metadata: HTMLMetadata) -> None:
    # FIXME: Not idempotent
    if metadata.text:
        if metadata.meta_desc is not None:
            combined_text = " ".join([metadata.meta_desc, metadata.text])
        else:
            combined_text = metadata.text
        fulltext_obj = FullText(
            url_uuid=metadata.url.url_uuid,
            crawl_uuid=crawl_uuid,
            inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
            full_text=combined_text,
            tsvector=func.to_tsvector(combined_text),
        )
        session.add(fulltext_obj)


def record_index_error(session: Session, crawl_uuid: UUID, message: str) -> None:
    session.add(IndexingError(crawl_uuid=crawl_uuid, description=message))


def have_icon_by_url(session: Session, url: URL) -> bool:
    """Return True if we think we already have an icon by that URL.

    Either as a domain level icon, or as a page level icon."""
    # FIXME: For now this is unimplemented
    return False


def have_icon_by_hash(session: Session, hash_bytes: bytes) -> bool:
    return session.query(
        session.query(Icon).filter(Icon.original_blake2b_hash == hash_bytes).exists()
    ).scalar()


def record_page_icon(session: Session, url: URL, hash_bytes: bytes, size: int) -> UUID:
    icon_uuid = uuid4()
    url_icon = URLIcon(url_uuid=url.url_uuid, icon_uuid=icon_uuid)
    icon = Icon(icon_uuid=icon_uuid, original_blake2b_hash=hash_bytes, pixel_size=size)
    session.add_all([icon, url_icon])
    return icon_uuid


def record_domain_icon(
    session: Session, icon_url: URL, hash_bytes: bytes, size: int
) -> UUID:
    icon_uuid = uuid4()
    domain_icon = DomainIcon(
        scheme=icon_url.scheme, netloc=icon_url.netloc, icon_uuid=icon_uuid
    )
    icon = Icon(icon_uuid=icon_uuid, original_blake2b_hash=hash_bytes, pixel_size=size)
    session.add_all([icon, domain_icon])
    return icon_uuid
