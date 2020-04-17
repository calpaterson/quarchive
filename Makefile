default: build
.PHONY: build default

# Server
# ------
py_files := $(shell find src/server -name '*.py' -not -path "src/server/.tox/*" -not -path "src/server/build/**")
server_version_file := src/server/VERSION
server_version := $(shell cat $(server_version_file))
artefact := quarchive-$(server_version)-py3-none-any.whl

dist/$(artefact): $(py_files) $(server_version_file) | dist
	cd src/server; tox
	mv src/server/dist/$(artefact) dist/

# Extension
# ---------
ext_path := src/extension
web_ext := $(ext_path)/node_modules/web-ext/bin/web-ext
eslint := $(ext_path)/node_modules/eslint/bin/eslint.js
tsc := $(ext_path)/node_modules/typescript/bin/tsc
jest := $(ext_path)/node_modules/jest/bin/jest.js
ts_files := $(wildcard $(ext_path)/src/*.ts)
js_files := $(addprefix $(ext_path)/build/, $(notdir $(ts_files:ts=js)))
extension_version_file := $(ext_path)/VERSION
extension_version := $(shell cat $(extension_version_file))
extension_manifest := $(ext_path)/build/manifest.json
extension_manifest_template := $(ext_path)/manifest.json.template
extension_build_dir := $(ext_path)/build
jest_sentinel := $(ext_path)/.jest-sentinel

dist/quarchive-$(extension_version).zip: $(ext_path)/webextconfig.js $(web_ext) $(js_files) $(ext_path)/options.html $(extension_manifest) $(jest_sentinel) | dist
	cp $(ext_path)/options.html $(extension_build_dir)/options.html
	cd $(ext_path)/; $(realpath $(web_ext)) build -c $(realpath $<)

$(js_files): $(ext_path)/tsconfig.json $(ts_files) $(tsc)
	$(tsc) --build $<

$(ext_html_files):

$(jest_sentinel): $(ext_path)/jest.config.js $(ts_files) $(jest)
	$(jest) -c $<
	touch $@

# $(ext_path)/.eslint-sentinel: $(eslint) $(js_files)
# 	$(eslint) -f unix $(ext_path)/quarchive-background.js $(ext_path)/quarchive-options.js
# 	touch $@

$(extension_manifest): $(extension_manifest_template) $(extension_version_file)
	sed 's/$$VERSION/$(extension_version)/' $(extension_manifest_template) > $@

$(web_ext) $(tsc) $(eslint) $(jest):
	cd $(ext_path); npm install --save-dev

dist $(extension_build_dir):
	mkdir -p $@

build: dist/quarchive-$(extension_version).zip dist/$(artefact)
