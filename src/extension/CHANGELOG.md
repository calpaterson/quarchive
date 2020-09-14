# Changelog

This is the changelog for the web browser extension part of Quarchive.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Canonicalise URLs once they enter the extension and use them with the backend (eg: no trailing # or ?)

## [1.0.0] - 2020-05-21
### Changed

- Sync via jsonlines instead of json objects.  Eventually this may help speed up big syncs.

### Added

- Report extension version to the server when syncing.  This will aid debugging of extension issues.

## [0.9.2] - 2020-04-27

- First (public) version
