FROM python:3.7-slim-buster
COPY dist/quartermarker-0.0.1.pex quartermarker-0.0.1.pex
CMD ./quartermarker-0.0.1.pex
