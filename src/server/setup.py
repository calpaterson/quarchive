"""A setuptools based setup module.

See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name='quartermarker',
    version='0.0.1',
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "quartermarker=quartermarker:main",
        ]
    },
)
