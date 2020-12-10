from typing import Optional, Any

import flask

from quarchive.value_objects import User


def get_current_user() -> User:
    """Utility function to get the current user.

    The only purpose of this is for typing - flask.g.user is unavoidably Any
    whereas the return type of this is User.

    """
    return flask.g.user


def set_current_user(user: User, api_key: bytes, session: Optional[Any] = None):
    """Sets the current user.

    Optional session kwarg is to facilitate use from tests."""
    if session is None:
        session = flask.session

    flask.g.user = user
    flask.g.sync_credentials = "|".join([user.username, api_key.hex()])
    session["user_uuid"] = user.user_uuid
    # Make it last for 31 days
    session.permanent = True
