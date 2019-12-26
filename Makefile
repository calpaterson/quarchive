web_ext := src/extension/node_modules/web-ext/bin/web-ext
eslint := src/extension/node_modules/eslint/bin/eslint.js
commit := $(shell git rev-parse --short HEAD)
artefact := quarchive-0.0.1-py3-none-any.whl

.PHONY: build docker

build: dist/quartermarker-0.1.zip dist/$(artefact)

lint: $(eslint)
	$(eslint) -f unix src/extension/quartermarker.js src/extension/options.js

docker: dist/quarchive-$(commit).docker

dist/quarchive-$(commit).docker: dist/$(artefact)
	docker build . -t make-temp:latest
	docker save make-temp:latest | gzip > $@

dist/$(artefact): src/server src/server/quarchive/__init__.py | dist
	cd src/server; tox
	mv src/server/dist/$(artefact) dist/

dist/quartermarker-0.1.zip: src/extension/ $(web_ext) src/extension/quartermarker.js | dist
	$(web_ext) build -a dist -s src/extension/ --overwrite-dest

$(web_ext):
	cd src/extension; npm install --save-dev web-ext

$(eslint):
	cd src/extension; npm install --save-dev eslint

dist:
	mkdir -p dist
