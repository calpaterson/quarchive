from typing import Optional, Any

import flask

from quarchive.value_objects import User


def get_current_user() -> Optional[User]:
    """Utility function to get the current user.

    The only purpose of this is for typing - flask.g.user is unavoidably Any
    whereas the return type of this is User.

    """
    return flask.g.get("_quarchive_user", None)


def set_current_user(user: User) -> None:
    """Sets the current user."""
    flask.g._quarchive_user = user
