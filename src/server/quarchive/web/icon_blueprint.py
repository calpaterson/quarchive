from uuid import UUID
from logging import getLogger

import flask

from quarchive import file_storage

log = getLogger(__name__)

icon_blueprint = flask.Blueprint("quarchive-icons", "quarchive-icons")


@icon_blueprint.route("/icons/<uuid:icon_uuid>.png")
def icon_by_uuid(icon_uuid: UUID) -> flask.Response:
    # This endpoint is added for completeness.  In production icons should not
    # be served from Python
    log.warning("serving icon %s directly", icon_uuid)

    bucket = file_storage.get_icon_bucket()
    icon_filelike = file_storage.download_icon(bucket, icon_uuid)
    response = flask.Response(icon_filelike, mimetype="image/png")

    # But if we're going to serve these, just serve them once
    ONE_YEAR = 366 * 24 * 60 * 60
    response.cache_control.max_age = ONE_YEAR
    response.cache_control.public = True
    return response
