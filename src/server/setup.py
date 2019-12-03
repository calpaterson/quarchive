from setuptools import setup, find_packages

setup(
    name="quartermarker",
    version="0.0.1",
    packages=find_packages(),
    install_requires=["flask~=1.1.1", "flask-cors~=3.0.8"],
    extras_require={
        "tests": ["pytest~=5.3.1", "pytest-flask~=0.15.0", "hypothesis~=4.50.6"],
        "dev": ["black~=19.10b0", "mypy~=0.750"],
    },
    entry_points={"console_scripts": ["quartermarker=quartermarker:main",]},
)
