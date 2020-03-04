from setuptools import setup, find_packages

VERSION = open("VERSION").read().strip()

setup(
    name="quarchive",
    version=VERSION,
    packages=find_packages(exclude=["tests.*", "tests"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "flask-sqlalchemy~=2.4.1",
        "flask~=1.1.1",
        "flask-cors~=3.0.8",
        "sqlalchemy~=1.3.11",
        "psycopg2~=2.8.4",
        "babel~=2.7.0",
        "click~=7.0.0",
        "python-dateutil~=2.8.1",
        "celery~=4.4.0",
        "requests~=2.22.0",
        "boto3~=1.11.0",
        "lxml~=4.4.2",
        "missive~=0.5",
    ],
    extras_require={
        "tests": [
            "pytest-env~=0.6.2",
            "pytest~=5.3.1",
            "pytest-flask~=0.15.0",
            "hypothesis~=4.50.6",
            "alembic~=1.3.1",
            "cssselect~=1.1.0",
            "freezegun~=0.3.12",
            "responses~=0.10.9",
            "moto~=1.3.14",
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
            "quarchive=quarchive:main",
            "qm-pinboard-import=quarchive:pinboard_import",
            "quarchive-message-processor=quarchive:message_processor",
        ]
    },
)
