web_ext := src/extension/node_modules/web-ext/bin/web-ext
eslint := src/extension/node_modules/eslint/bin/eslint.js
tsc := src/extension/node_modules/typescript/bin/tsc
commit := $(shell git rev-parse --short HEAD)
ts_files := $(wildcard src/extension/*.ts)
js_files := $(ts_files:ts=js)
py_files := $(shell find src/server -name '*.py' -not -path "src/server/.tox/*" -not -path "src/server/build/**")
server_version_file := src/server/VERSION
server_version := $(shell cat $(server_version_file))
artefact := quarchive-$(server_version)-py3-none-any.whl
extension_version_file := src/extension/VERSION
extension_version := $(shell cat $(extension_version_file))
extension_manifest := src/extension/manifest.json
extension_manifest_template := src/extension/manifest.json.template

.PHONY: build

build: dist/quarchive-$(extension_version).zip dist/$(artefact)

dist:
	mkdir -p dist

# Server build steps
dist/$(artefact): $(py_files) $(server_version_file) | dist
	cd src/server; tox
	mv src/server/dist/$(artefact) dist/

# Extension build steps
dist/quarchive-$(extension_version).zip: $(web_ext) $(js_files) $(extension_manifest) | dist
	$(web_ext) build -a dist -s src/extension/ -i package.json -i package-lock.json -i manifest.json.template -i VERSION --overwrite-dest

$(js_files): src/extension/tsconfig.json $(ts_files)
	$(tsc) --build src/extension/tsconfig.json

src/extension/.eslint-sentinel: $(eslint) $(js_files)
	$(eslint) -f unix src/extension/quarchive-background.js src/extension/quarchive-options.js
	touch $@

$(extension_manifest): $(extension_manifest_template) $(extension_version_file)
	sed 's/$$VERSION/$(extension_version)/' $(extension_manifest_template) > $@

$(web_ext) $(tsc) $(eslint):
	cd src/extension; npm install --save-dev
