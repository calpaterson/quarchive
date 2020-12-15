# Changelog

This is the changelog for the web browser extension part of Quarchive.

The format is based on [Keep a
Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) **for the browser
extension only**.

## Unreleased

- Check with the server whether we need to sync before doing a full sync
  - In future this will be used to prevent needless full syncs
- Use the `/api/` prefixed sync endpoint urls
- Keep a unique internal client id
  - This will be used to report to web users what clients are currently syncing
  - It's displayed on the options page
- Report the last full sync time on the options page
  - This is purely for debugging and diagnosics

## [1.3.0] - 2020-09-26

- Clear indexed db on upgrade
  - necessary because old uri's and other nonsense will be sitting in there
  - internal idb schema is now version 4

## [1.2.0] - 2020-09-26 (never released)

- Ignore all bookmarks that have a scheme other than http or https
  - quarchive server is about to drop support for these
  - fixes bug [#15](https://github.com/calpaterson/quarchive/issues/15)

## [1.1.0] - 2020-09-14

- Canonicalise URLs once they enter the extension and use them with the backend (eg: no trailing # or ?)

## [1.0.0] - 2020-05-21
### Changed

- Sync via jsonlines instead of json objects.  Eventually this may help speed up big syncs.

### Added

- Report extension version to the server when syncing.  This will aid debugging of extension issues.

## [0.9.2] - 2020-04-27

- First (public) version
