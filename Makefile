web_ext := src/extension/node_modules/web-ext/bin/web-ext
eslint := src/extension/node_modules/eslint/bin/eslint.js
commit := $(shell git rev-parse --short HEAD)
artefact := quarchive-0.0.1-py3-none-any.whl
js_files := $(wildcard src/extension/*.js)
py_files := $(shell find src/server -name '*.py' -not -path "src/server/.tox/*" -not -path "src/server/build/**")
extension_version_file := src/extension/VERSION
extension_version := $(shell cat $(extension_version_file))
extension_manifest := src/extension/manifest.json
extension_manifest_template := src/extension/manifest.json.template

.PHONY: build

build: dist/quarchive-$(extension_version).zip dist/$(artefact)

dist:
	mkdir -p dist

# Server build steps
dist/$(artefact): $(py_files) | dist
	cd src/server; tox
	mv src/server/dist/$(artefact) dist/

# Extension build steps
dist/quarchive-$(extension_version).zip: $(web_ext) $(js_files) src/extension/.eslint-sentinel $(extension_manifest) | dist
	$(web_ext) build -a dist -s src/extension/ -i package.json -i package-lock.json -i manifest.json.template -i VERSION --overwrite-dest

src/extension/.eslint-sentinel: $(eslint) $(js_files)
	$(eslint) -f unix src/extension/quarchive-background.js src/extension/quarchive-options.js
	touch $@

$(extension_manifest): $(extension_manifest_template) $(extension_version_file)
	sed 's/$$VERSION/$(extension_version)/' $(extension_manifest_template) > $@

$(web_ext):
	cd src/extension; npm install --save-dev web-ext

$(eslint):
	cd src/extension; npm install --save-dev eslint
