BEGIN;

ALTER TABLE bookmarks DROP CONSTRAINT bookmarks_url_fkey;

ALTER TABLE crawl_requests DROP CONSTRAINT crawl_requests_url_uuid_fkey;

ALTER TABLE full_text DROP CONSTRAINT full_text_url_uuid_fkey;

UPDATE urls
SET url_uuid = to_uuid
FROM url_fixes
WHERE url_uuid = from_uuid
;

UPDATE bookmarks
SET url_uuid = to_uuid
FROM url_fixes
WHERE url_uuid = from_uuid
;


UPDATE crawl_requests
SET url_uuid = to_uuid
FROM url_fixes
WHERE url_uuid = from_uuid
;

UPDATE full_text
SET url_uuid = to_uuid
FROM url_fixes
WHERE url_uuid = from_uuid
;

ALTER TABLE bookmarks
ADD CONSTRAINT bookmarks_url_fkey
FOREIGN KEY (url_uuid) REFERENCES urls (url_uuid);

ALTER TABLE crawl_requests
ADD CONSTRAINT crawl_requests_url_uuid_fkey
FOREIGN KEY (url_uuid) REFERENCES urls (url_uuid);

ALTER TABLE full_text
ADD CONSTRAINT full_text_url_uuid_fkey
FOREIGN KEY (url_uuid) REFERENCES urls (url_uuid);

-- ROLLBACK;
