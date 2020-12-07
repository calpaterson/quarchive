from uuid import UUID
from os import environ
from logging import getLogger
from functools import lru_cache
from typing import BinaryIO, IO, Optional
import tempfile
import shutil
import gzip

import boto3
import botocore.exceptions as boto_exceptions
from botocore.utils import fix_s3_host

from quarchive.io import RewindingIO

log = getLogger(__name__)


class FileStorageException(Exception):
    """Indicates something went wrong in here.

    Custom exception used to keep the horrors of boto contained within this
    file.

    """

    def __init__(self, message):
        super().__init__(self)
        self.message = message


@lru_cache(1)
def get_s3():
    session = boto3.Session(
        aws_access_key_id=environ["QM_AWS_ACCESS_KEY"],
        aws_secret_access_key=environ["QM_AWS_SECRET_ACCESS_KEY"],
        region_name=environ["QM_AWS_REGION_NAME"],
    )

    # This is a magic value to facilitate testing
    resource_kwargs = {}
    if environ["QM_AWS_S3_ENDPOINT_URL"] != "UNSET":
        resource_kwargs["endpoint_url"] = environ["QM_AWS_S3_ENDPOINT_URL"]

    resource = session.resource("s3", **resource_kwargs)
    resource.meta.client.meta.events.unregister("before-sign.s3", fix_s3_host)
    log.debug("constructed s3 resource")
    return resource


@lru_cache(1)
def get_response_body_bucket():
    bucket = get_s3().Bucket(environ["QM_RESPONSE_BODY_BUCKET_NAME"])
    log.debug("constructed response body bucket")
    return bucket


def get_icon_bucket():
    bucket = get_s3().Bucket(environ["QM_ICON_BUCKET_NAME"])
    log.debug("constructed response body bucket")
    return bucket


def upload_file(bucket, filelike: BinaryIO, filename: str) -> None:
    """Upload a fileobj into the bucket (compressed)"""
    with tempfile.TemporaryFile(mode="w+b") as temp_file:
        gzip_fileobj = gzip.GzipFile(mode="w+b", fileobj=temp_file)
        shutil.copyfileobj(filelike, gzip_fileobj)
        gzip_fileobj.close()
        temp_file.seek(0)
        bucket.upload_fileobj(temp_file, Key=filename)
    log.debug("uploaded '%s' to '%s'", filename, bucket.name)


def download_file(bucket, filename: str) -> gzip.GzipFile:
    """Download a fileobj from a bucket (decompressed)"""
    temp_file = tempfile.TemporaryFile(mode="w+b")
    try:
        bucket.download_fileobj(filename, temp_file)
    except boto_exceptions.ClientError:
        raise FileStorageException(f"unable to download '{filename}' from '{bucket}'")
    temp_file.seek(0)
    gzip_fileobj = gzip.GzipFile(mode="r+b", fileobj=temp_file)
    log.debug("downloaded '%s' from '%s'", filename, bucket.name)
    return gzip_fileobj


def upload_icon(bucket, icon_uuid: UUID, filelike: IO[bytes]) -> None:
    """Upload an icon into the bucket.

    Icon's aren't compressed (they're already pngs) and they have their
    Content-Type set."""
    bucket.upload_fileobj(
        filelike, Key=f"{icon_uuid}.png", ExtraArgs=dict(ContentType="image/png")
    )
    log.debug("uploaded icon %s", icon_uuid)


def download_icon(bucket, icon_uuid: UUID) -> Optional[IO[bytes]]:
    rewinder = RewindingIO(tempfile.TemporaryFile())
    with rewinder as temp_file:
        bucket.download_fileobj(f"{icon_uuid}.png", temp_file)
    return rewinder.io
