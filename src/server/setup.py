from setuptools import setup, find_packages

setup(
    name='quartermarker',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        "flask~=1.1.1",
        "flask-cors~=3.0.8",
    ],
    entry_points={
        "console_scripts": [
            "quartermarker=quartermarker:main",
        ]
    },
)
