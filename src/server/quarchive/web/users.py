from typing import Optional, Any

import flask

from quarchive.value_objects import User


def get_current_user() -> User:
    """Utility function to get the current user.

    The only purpose of this is for typing - flask.g.user is unavoidably Any
    whereas the return type of this is User.

    """
    return flask.g._quarchive_user


def set_current_user(user: User):
    """Sets the current user."""
    flask.g._quarchive_user = user
