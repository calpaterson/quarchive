from setuptools import setup, find_packages

VERSION = open("VERSION").read().strip()

setup(
    name="quarchive",
    version=VERSION,
    packages=find_packages(exclude=["tests.*", "tests"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "PyYaml~=5.3.1",
        "flask-sqlalchemy~=2.4.1",
        "flask~=1.1.1",
        "flask-cors~=3.0.8",
        "sqlalchemy~=1.3.11",
        "psycopg2~=2.8.4",
        "babel~=2.7.0",
        "Flask-Babel~=1.0.0",
        "click~=7.0.0",
        "python-dateutil~=2.8.1",
        "pytz",
        "requests~=2.22.0",
        "boto3~=1.11.0",
        "lxml~=4.4.2",
        "missive~=0.6.0",
        "passlib~=1.7.2",
        "bcrypt~=3.1.7",
        "python-magic~=0.4.15",
        "pyhash~=0.9.3",
        "pyappcache~=0.1",
        "kombu~=4.6.8",
        "attrs~=20.2.0",
    ],
    extras_require={
        "tests": [
            "pytest-xdist~=1.32.0",
            "pytest-env~=0.6.2",
            "pytest~=5.3.1",
            "pytest-flask~=0.15.0",
            "hypothesis~=4.50.6",
            "alembic~=1.3.1",
            "cssselect~=1.1.0",
            "freezegun~=0.3.12",
            "responses~=0.10.9",
            "moto~=1.3.16",
        ],
        "dev": [
            "wheel~=0.33.6",
            "black~=19.10b0",
            "mypy~=0.750",
            "sqlalchemy-stubs~=0.3",
            "bpython~=0.18",
            "alembic~=1.3.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "quarchive=quarchive.local:main",
            "quarchive-url-recheck=quarchive:url_recheck",
            "qm-pinboard-import=quarchive.pinboard:pinboard_import",
            "quarchive-send-hello=quarchive.messaging.publication:send_hello",
            "quarchive-bg-worker=quarchive.bg_worker:bg_worker",
        ]
    },
)
