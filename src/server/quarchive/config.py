import configparser
from logging import getLogger
from os import environ, path
from typing import Optional

log = getLogger(__name__)


REQUIRED_CONFIG_KEYS = {
    "QM_SQL_URL",
    "QM_SECRET_KEY",
    "QM_RESPONSE_BODY_BUCKET_NAME",
    "QM_AWS_ACCESS_KEY",
    "QM_AWS_REGION_NAME",
    "QM_AWS_SECRET_ACCESS_KEY",
    "QM_AWS_S3_ENDPOINT_URL",
}


def load_config(env_ini: Optional[str] = None) -> None:
    if env_ini is not None:
        log.info("loading from %s", path.abspath(env_ini))
        parser = configparser.ConfigParser()
        # mypy confused by this unusual pattern
        # https://github.com/python/mypy/issues/708
        parser.optionxform = str  # type: ignore
        parser.read(env_ini)
        environ.update(parser["env"].items())
    else:
        log.warning("not loading env from any config file")

    if not REQUIRED_CONFIG_KEYS.issubset(set(environ.keys())):
        missing_keys = REQUIRED_CONFIG_KEYS.difference(set(environ.keys()))
        raise RuntimeError("incomplete configuration! missing keys: %s" % missing_keys)
