#!/usr/bin/env python3
"""One off script to help in the task of converting url uuids from uuid4 to
proper url uuids."""

import sys
import csv
from urllib.parse import urlunsplit
from uuid import uuid4, UUID, uuid5, NAMESPACE_URL as UUID_URL_NAMESPACE


def create_url_uuid(url: str) -> UUID:
    # Use uuid5's namespace system to make url uuid deterministic
    return uuid5(UUID_URL_NAMESPACE, url)


def main():
    reader = csv.DictReader(sys.stdin)
    writer = csv.writer(sys.stdout)
    writer.writerow(["from_uuid", "to_uuid"])
    for line in reader:
        current_uuid = UUID(line["url_uuid"])
        url = urlunsplit((
            line["scheme"],
            line["netloc"],
            line["path"],
            line["query"],
            line["fragment"],
        ))

        expected_uuid = create_url_uuid(url)

        if expected_uuid != current_uuid:
            writer.writerow([current_uuid, expected_uuid])

if __name__ == "__main__":
    main()
