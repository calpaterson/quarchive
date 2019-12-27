web_ext := src/extension/node_modules/web-ext/bin/web-ext
eslint := src/extension/node_modules/eslint/bin/eslint.js
commit := $(shell git rev-parse --short HEAD)
artefact := quarchive-0.0.1-py3-none-any.whl
js_files := $(wildcard src/extension/*.js)

.PHONY: build docker

build: dist/quarchive-0.0.1.zip dist/$(artefact)

src/extension/.eslint-sentinel: $(eslint) $(js_files)
	$(eslint) -f unix src/extension/quarchive-background.js src/extension/quarchive-options.js
	touch $@

docker: dist/quarchive-$(commit).docker

dist/quarchive-$(commit).docker: dist/$(artefact)
	docker build . -t make-temp:latest
	docker save make-temp:latest | gzip > $@

dist/$(artefact): src/server src/server/quarchive/__init__.py | dist
	cd src/server; tox
	mv src/server/dist/$(artefact) dist/

dist/quarchive-0.0.1.zip: $(web_ext) $(js_files) src/extension/.eslint-sentinel | dist
	$(web_ext) build -a dist -s src/extension/ -i package.json -i package-lock.json --overwrite-dest

$(web_ext):
	cd src/extension; npm install --save-dev web-ext

$(eslint):
	cd src/extension; npm install --save-dev eslint

dist:
	mkdir -p dist
