from os import environ
import secrets
from logging import getLogger
from typing import Any, Iterable, Optional, Set, Tuple, Dict, cast
from uuid import UUID, uuid4
from datetime import datetime, timezone
from time import monotonic_ns
from dataclasses import dataclass

import pytz
from pyappcache.cache import Cache
from pyappcache.keys import BaseKey
from sqlalchemy import and_, cast as sa_cast, func, types as satypes, create_engine
from sqlalchemy.sql.expression import case
from sqlalchemy.dialects.postgresql import (
    ARRAY as PGARRAY,
    array as pg_array,
    insert as pg_insert,
)
from sqlalchemy.orm import sessionmaker, Session

from quarchive.accesscontrol import (
    AccessObject,
    Access,
    ShareGrant,
    BookmarkAccessObject,
)
from .cache_namespaces import UserBookmarksNamespaceKey
from quarchive.html_metadata import HTMLMetadata
from quarchive.value_objects import (
    Bookmark,
    Request,
    URL,
    User,
)

from .models import (
    APIKey,
    BookmarkTag,
    CanonicalUrl,
    CrawlRequest,
    CrawlResponse,
    DomainIcon,
    FullText,
    Icon,
    IconSource,
    IndexingError,
    Link,
    SQLABookmark,
    SQLAUrl,
    SQLAccessObject,
    SQLShareGrant,
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


class UserUUIDToUserKey(BaseKey[User]):
    def __init__(self, user_uuid: UUID):
        self._user_uuid = user_uuid

    def cache_key_segments(self):
        return [str(self._user_uuid)]


class UsernameToUserKey(BaseKey[User]):
    def __init__(self, username: str):
        self._username = username

    def cache_key_segments(self):
        return [self._username]


class UsernameToApiKey(BaseKey[bytes]):
    def __init__(self, username: str):
        self._username = username

    def cache_key_segments(self):
        return [self._username, "api_key"]


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

    user_tuple = (
        session.query(
            SQLUser.user_uuid,
            UserEmail.email_address,
            SQLUser.timezone,
            SQLUser.registered,
        )
        .outerjoin(UserEmail)
        .filter(SQLUser.username == username)
        .first()
    )

    # User doesn't exist
    if user_tuple is None:
        return None

    user_uuid, email, timezone, registered = user_tuple

    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
        registered=registered,
    )
    put_user_in_cache(cache, user)
    return user


def user_from_user_uuid(session, cache: Cache, user_uuid: UUID) -> Optional[User]:
    # FIXME: This should return a nullable type as the user for this user uuid
    # may have been deleted (among other things)
    key = UserUUIDToUserKey(user_uuid)
    user = cache.get(key)
    if user is not None:
        return user

    row = (
        session.query(
            SQLUser.username,
            UserEmail.email_address,
            SQLUser.timezone,
            SQLUser.registered,
        )
        .outerjoin(UserEmail)
        .filter(SQLUser.user_uuid == user_uuid)
        .one_or_none()
    )
    if row is None:
        return row
    else:
        username, email, timezone, registered = row
    user = User(
        user_uuid=user_uuid,
        username=username,
        email=email,
        timezone=pytz.timezone(timezone),
        registered=registered,
    )
    put_user_in_cache(cache, user)
    return user


def is_correct_password(session, crypt_context, user: User, password: str) -> bool:
    (db_password,) = (
        session.query(SQLUser.password)
        .filter(SQLUser.user_uuid == user.user_uuid)
        .one()
    )
    return crypt_context.verify(password, db_password)


def set_password(
    session: Session, crypt_context: Any, user: User, new_password: str
) -> None:
    new_password_hashed = crypt_context.hash(new_password)
    session.query(SQLUser).filter(SQLUser.user_uuid == user.user_uuid).update(
        dict(password=new_password_hashed)
    )
    log.warning("set password for %s", user)


def create_user(
    session: Session,
    cache: Cache,
    crypt_context: Any,
    username: str,
    password_plain: str,
    email: Optional[str] = None,
    user_timezone="Europe/London",
) -> Tuple[User, bytes]:
    """Creates a new user, returns User object and api_key"""
    user_uuid = uuid4()

    key = UserUUIDToUserKey(user_uuid)

    password_hashed = crypt_context.hash(password_plain)
    registered = datetime.utcnow().replace(tzinfo=timezone.utc)
    # FIXME: accept timezone as an argument (infer it somehow, from IP
    # address?)
    sql_user = SQLUser(
        user_uuid=user_uuid,
        username=username,
        password=password_hashed,
        timezone=user_timezone,
        registered=registered,
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
        timezone=pytz.timezone(user_timezone),
        registered=registered,
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
        .on_conflict_do_nothing(index_elements=["url_uuid"])
    )
    session.execute(url_stmt)

    return url.url_uuid


def upsert_urls(session: Session, urls: Iterable[URL]):
    """Upsert urls en masse"""
    values = [
        dict(
            url_uuid=url.url_uuid,
            scheme=url.scheme,
            netloc=url.netloc,
            path=url.path,
            query=url.query,
            fragment=url.fragment,
        )
        for url in urls
    ]
    url_stmt = (
        pg_insert(SQLAUrl.__table__)
        .values(values)
        .on_conflict_do_nothing(index_elements=["url_uuid"])
    )
    session.execute(url_stmt)
    log.info("upserted %d urls", len(values))


def get_url_by_url_uuid(session: Session, url_uuid: UUID) -> Optional[URL]:
    """Get a URL object by url uuid"""
    sqla_url: Optional[SQLAUrl] = session.query(SQLAUrl).filter(
        SQLAUrl.url_uuid == url_uuid
    ).first()
    if sqla_url is not None:
        return sqla_url.to_url()
    return None


def set_bookmark(
    session: Session, cache: Cache, user_uuid: UUID, bookmark: Bookmark
) -> UUID:
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

    ub_cache_ns = UserBookmarksNamespaceKey(user_uuid)
    cache.set(ub_cache_ns, monotonic_ns())

    return url.url_uuid


@dataclass
class MergeResult:
    changed: Set[Bookmark]
    added: Set[Bookmark]


def merge_bookmarks(
    session: Session,
    cache: Cache,
    user_uuid: UUID,
    recieved_bookmarks: Iterable[Bookmark],
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
            set_bookmark(session, cache, user_uuid, recieved)
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
                set_bookmark(session, cache, user_uuid, merged)
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
        .filter(~BookmarkTag.deleted)
        .group_by(Tag.tag_name)
        .order_by(func.count(Tag.tag_name).desc())
    )
    return query


def user_tags(session, user: User) -> Iterable[str]:
    """Return an iterable of all tags that a user is currently using."""
    query = (
        session.query(Tag.tag_name)
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
        .filter(~BookmarkTag.deleted)
    )
    for (tag,) in query:
        yield tag


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


def delete_bookmark(session, cache, user_uuid: UUID, url_uuid: UUID):
    """Delete a bookmark by user_uuid and url_uuid.  For test purposes only"""
    log.warning("deleting bookmark: %s %s", user_uuid, url_uuid)
    query = session.query(SQLABookmark).filter(
        SQLABookmark.url_uuid == url_uuid, SQLABookmark.user_uuid == user_uuid
    )
    query.delete(synchronize_session="fetch")

    cache.set(UserBookmarksNamespaceKey(user_uuid), monotonic_ns)


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


def most_recent_successful_bookmark_crawls(session: Session) -> Iterable[UUID]:
    query = """
    SELECT DISTINCT ON (url_uuid) crawl_uuid
    FROM crawl_requests
    JOIN crawl_responses USING (crawl_uuid)
    JOIN bookmarks USING (url_uuid)
    WHERE got_response
    AND status_code BETWEEN 200 AND 299
    ORDER BY url_uuid, requested DESC;
    """
    yield from (crawl_uuid for crawl_uuid, in session.execute(query))


def create_crawl_request(session: Session, crawl_uuid: UUID, request: Request):
    """Record a request that was made"""
    upsert_url(session, request.url)
    crawl_request = CrawlRequest(
        crawl_uuid=crawl_uuid,
        url_uuid=request.url.url_uuid,
        requested=datetime.utcnow().replace(tzinfo=timezone.utc),
        got_response=False,
    )
    session.add(crawl_request)


def mark_crawl_request_with_response(session: Session, crawl_uuid: UUID) -> None:
    """Mark the crawl request as having gotten a response"""
    # Can't be null here - we have a uuid.  If it is null that's a programming
    # error and don't except anything to catch that.
    crawl_request = cast(CrawlRequest, session.query(CrawlRequest).get(crawl_uuid))
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


def get_most_recent_crawl(session: Session, url: URL) -> UUID:
    return (
        session.query(CrawlResponse.crawl_uuid,)
        .join(CrawlRequest)
        .join(SQLAUrl)
        .filter(SQLAUrl.url_uuid == url.url_uuid)
        .order_by(CrawlRequest.requested)
        .limit(1)
        .scalar()
    )


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
    # FIXME: Need proper tests
    if metadata.text:
        if metadata.meta_desc is not None:
            combined_text = " ".join([metadata.meta_desc, metadata.text])
        else:
            combined_text = metadata.text
        fulltext_obj = session.query(FullText).get(metadata.url.url_uuid)
        if fulltext_obj is None:
            fulltext_obj = FullText(
                url_uuid=metadata.url.url_uuid, crawl_uuid=crawl_uuid
            )
            session.add(fulltext_obj)

        fulltext_obj.crawl_uuid = crawl_uuid
        fulltext_obj.inserted = datetime.utcnow().replace(tzinfo=timezone.utc)
        fulltext_obj.full_text = combined_text
        fulltext_obj.tsvector = func.to_tsvector(combined_text)

    upsert_links(session, metadata.url, metadata.links)

    if metadata.canonical is not None:
        upsert_url(session, metadata.canonical)
        canonical_url_obj = (
            session.query(CanonicalUrl)
            .filter(CanonicalUrl.non_canonical_url_uuid == metadata.url.url_uuid)
            .first()
        )
        if canonical_url_obj is None:
            session.add(
                CanonicalUrl(
                    non_canonical_url_uuid=metadata.url.url_uuid,
                    canonical_url_uuid=metadata.canonical.url_uuid,
                )
            )
            log.debug("new canonical url %s for %s", metadata.canonical, metadata.url)
        else:
            canonical_url_obj.canonical_url_uuid = metadata.canonical.url_uuid

    # FIXME: invalidate caches for all users with this bookmark?


def upsert_links(session: Session, url: URL, links: Set[URL]) -> None:
    current: Set[UUID] = set(
        t
        for t, in session.query(Link.to_url_uuid).filter(
            Link.from_url_uuid == url.url_uuid
        )
    )
    required: Set[UUID] = {u.url_uuid for u in links}

    to_be_added: Set[UUID] = set()

    for link_url in links:
        if link_url.url_uuid in current:
            log.debug("not re-adding link from %s to %s", url, link_url)
        else:
            upsert_url(session, link_url)
            to_be_added.add(link_url.url_uuid)
            log.debug("added link from %s to %s", url, link_url)

    to_be_removed: Set[UUID] = current.difference(required)
    log.debug("deleting %d now absent links", len(to_be_removed))
    session.query(Link).filter(Link.to_url_uuid.in_(to_be_removed)).delete(
        synchronize_session="fetch"
    )

    session.add_all(
        [Link(from_url_uuid=url.url_uuid, to_url_uuid=r) for r in to_be_added]
    )

    # FIXME: invalidate caches for all users with this bookmark?


def record_index_error(session: Session, crawl_uuid: UUID, message: str) -> None:
    session.add(IndexingError(crawl_uuid=crawl_uuid, description=message))


def icon_at_url(session: Session, url: URL) -> Optional[UUID]:
    """Return icon_uuid if we think we already have an icon from that URL."""
    rv = (
        session.query(IconSource.icon_uuid)
        .filter(IconSource.url_uuid == url.url_uuid)
        .first()
    )
    if rv is not None:
        return rv[0]
    else:
        return None


def upsert_icon_for_url(session, page_url: URL, icon_uuid: UUID) -> None:
    url_icon = (
        session.query(URLIcon).filter(URLIcon.url_uuid == page_url.url_uuid).first()
    )
    if url_icon is None:
        url_icon = URLIcon(url_uuid=page_url.url_uuid, icon_uuid=icon_uuid)
        session.add(url_icon)
    else:
        url_icon.icon_uuid = icon_uuid

    # FIXME: invalidate caches for all users with this bookmark?


def have_icon_by_hash(session: Session, hash_bytes: bytes) -> bool:
    return session.query(
        session.query(Icon).filter(Icon.source_blake2b_hash == hash_bytes).exists()
    ).scalar()


def upsert_icon(session, icon_url: URL, hash_bytes: bytes) -> UUID:
    icon = session.query(Icon).filter(Icon.source_blake2b_hash == hash_bytes).first()
    if icon is None:
        icon = Icon(icon_uuid=uuid4(), source_blake2b_hash=hash_bytes)
        session.add(icon)
    icon_source = (
        session.query(IconSource)
        .filter(IconSource.url_uuid == icon_url.url_uuid)
        .first()
    )
    if icon_source is None:
        session.add(IconSource(icon_uuid=icon.icon_uuid, url_uuid=icon_url.url_uuid))
    return icon.icon_uuid

    # FIXME: invalidate caches for all users with this bookmark?


def record_page_icon(
    session: Session, icon_url: URL, page_url: URL, hash_bytes: bytes
) -> UUID:
    icon_uuid = upsert_icon(session, icon_url, hash_bytes)
    # FIXME: This should probably call upsert_icon_for_url
    url_icon = URLIcon(url_uuid=page_url.url_uuid, icon_uuid=icon_uuid)
    session.add(url_icon)
    return icon_uuid

    # FIXME: invalidate caches for all users with this bookmark?


def record_domain_icon(session: Session, icon_url: URL, hash_bytes: bytes) -> UUID:
    icon_uuid = upsert_icon(session, icon_url, hash_bytes)
    domain_icon = DomainIcon(
        scheme=icon_url.scheme, netloc=icon_url.netloc, icon_uuid=icon_uuid
    )
    session.add(domain_icon)
    return icon_uuid

    # FIXME: invalidate caches for all users with this bookmark?


def create_share_grant(
    session: Session, access_object: AccessObject, access_verb: Access
) -> ShareGrant:
    # 18 bytes is still fairly secure (more bits of randomness than our uuids)
    # and encodes nicely in base64 without any '='s at the end which can be a
    # useability problem when copying and pasting
    SHARE_TOKEN_LENGTH = 18
    share_token = secrets.token_bytes(SHARE_TOKEN_LENGTH)

    access_obj_stmt = (
        pg_insert(SQLAccessObject.__table__)
        .values(
            access_object_name=access_object.name, params=access_object.to_params(),
        )
        .on_conflict_do_nothing(index_elements=["access_object_name", "params"])
        .returning(SQLAccessObject.__table__.c.access_object_id)
    )
    rs = session.execute(access_obj_stmt).fetchone()
    if rs is not None:
        (access_obj_id,) = rs
    else:
        access_obj_id = (
            session.query(SQLAccessObject.access_object_id)
            .filter(SQLAccessObject.access_object_name == access_object.name)
            .filter(SQLAccessObject.params == access_object.to_params())
            .scalar()
        )

    sql_share_grant = SQLShareGrant(
        access_object_id=access_obj_id,
        access_verb_id=int(access_verb),
        revoked=False,
        share_token=share_token,
    )
    session.add(sql_share_grant)

    return ShareGrant(
        share_token=sql_share_grant.share_token,
        expiry=None,
        access_object=access_object,
        access_verb=access_verb,
        revoked=sql_share_grant.revoked,
    )


def get_share_grant_by_token(
    session: Session, share_token: bytes
) -> Optional[ShareGrant]:
    rs = (
        session.query(
            SQLShareGrant.share_token,
            SQLShareGrant.revoked,
            SQLAccessObject.access_object_name,
            SQLAccessObject.params,
            SQLShareGrant.access_verb_id,
        )
        .join(
            SQLAccessObject,
            SQLShareGrant.access_object_id == SQLAccessObject.access_object_id,
        )
        .filter(SQLShareGrant.share_token == share_token)
        .first()
    )
    if rs is None:
        return None
    else:
        share_token, revoked, ao_name, ao_params, av_id = rs
        access_object = BookmarkAccessObject.from_params(ao_params)
        access_verb = Access(av_id)
        return ShareGrant(
            share_token=share_token,
            expiry=None,
            access_object=access_object,
            access_verb=access_verb,
            revoked=revoked,
        )
