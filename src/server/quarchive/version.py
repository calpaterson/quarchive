from os import path

VERSION = None


def get_version():
    global VERSION
    if VERSION is None:
        with open(path.join(path.dirname(__file__), "VERSION")) as version_f:
            VERSION = version_f.read().strip()
    return VERSION
