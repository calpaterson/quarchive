from setuptools import setup, find_packages

VERSION = open("VERSION").read().strip()

setup(
    name="quarchive",
    version=VERSION,
    packages=find_packages(exclude=["tests.*", "tests"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "Flask-Babel~=1.0.0",
        "Pillow~=8.0.1",
        "PyYaml~=5.3.1",
        "argon2_cffi~=20.1.0",
        "attrs~=20.2.0",
        "babel~=2.7.0",
        "bcrypt~=3.1.7",
        "boto3~=1.11.0",
        "click~=7.0.0",
        "commonmark~=0.9.1",
        "flask-cors~=3.0.8",
        "flask-sqlalchemy~=2.4.1",
        "flask~=1.1.1",
        "kombu~=5.0.0",
        "lxml~=4.4.2",
        "missive~=0.8.0",
        "passlib~=1.7.2",
        "psycopg2~=2.8.4",
        "pyappcache~=0.1",
        "pyhash~=0.9.3",
        "python-dateutil~=2.8.1",
        "python-magic~=0.4.15",
        "pytz",
        "requests~=2.22.0",
        "sqlalchemy~=1.3.11",
        "systemd-python==234",
        "werkzeug==0.16.1",
    ],
    extras_require={
        "tests": [
            "alembic~=1.3.1",
            "cssselect~=1.1.0",
            "freezegun~=0.3.12",
            "hypothesis~=4.50.6",
            "moto~=1.3.16",
            "pytest-env~=0.6.2",
            "pytest-flask~=0.15.0",
            "pytest-xdist~=1.32.0",
            "pytest~=5.3.1",
            "responses~=0.10.9",
        ],
        "dev": [
            "alembic~=1.3.1",
            "black~=19.10b0",
            "bpython~=0.18",
            "mypy==0.790",
            "sqlalchemy-stubs~=0.3",
            "wheel~=0.33.6",
        ],
    },
    entry_points={
        "console_scripts": [
            "quarchive=quarchive.cli:quarchive_cli",
            "qm-pinboard-import=quarchive.pinboard:pinboard_import",
            "quarchive-bg-worker=quarchive.bg_worker:bg_worker",
            "quarchive-get-crawl-body=quarchive.cli:get_crawl_body",
            "quarchive-reindex-url=quarchive.cli:reindex_url",
            "quarchive-reindex-bookmarks=quarchive.cli:reindex_bookmarks",
            "quarchive-url-recheck=quarchive:url_recheck",
        ]
    },
)
