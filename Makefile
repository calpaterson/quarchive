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
node_modules := $(ext_path)/node_modules
web_ext := $(node_modules)/web-ext/bin/web-ext
eslint := $(node_modules)/eslint/bin/eslint.js
tsc := $(node_modules)/typescript/bin/tsc
jest := $(node_modules)/jest/bin/jest.js
generate_manifest := $(ext_path)/generate-manifest

# Source files
jest_sentinel := $(ext_path)/.jest-sentinel
ts_files := $(wildcard $(ext_path)/src/*.ts)
icons := $(ext_path)/icons/48x48.png $(ext_path)/icons/96x96.png
html_files := $(wildcard $(ext_path)/src/*.html)
ext_version_file := $(ext_path)/VERSION
ext_version := $(shell cat $(ext_version_file))
webextension_polyfill := $(node_modules)/webextension-polyfill/dist/browser-polyfill.js

# Build files (firefox)
ext_firefox_build_dir := $(ext_path)/firefox-build
ext_firefox_js_files := $(addprefix $(ext_firefox_build_dir)/, $(notdir $(ts_files:ts=js)))
ext_firefox_manifest := $(ext_firefox_build_dir)/manifest.json

dist/quarchive-$(ext_version)-firefox.zip: $(ext_path)/firefox-webextconfig.js $(web_ext) $(ext_firefox_manifest) $(jest_sentinel) $(ext_firefox_js_files) $(html_files) $(icons) $(webextension_polyfill) | dist
	cp $(icons) $(webextension_polyfill) $(html_files) $(ext_firefox_build_dir)
	cd $(ext_path)/; $(realpath $(web_ext)) build -c $(realpath $<)
	mv $(ext_firefox_build_dir)/quarchive-$(ext_version).zip $@

$(ext_firefox_js_files): $(ext_path)/tsconfig-firefox.json $(ts_files) $(tsc) | $(ext_firefox_build_dir)
	$(tsc) --build $<

$(ext_firefox_manifest): $(generate_manifest) $(ext_version_file) | $(ext_firefox_build_dir)
	$(generate_manifest) firefox $(ext_version) > $@

# Build files (chrome)
ext_chrome_build_dir := $(ext_path)/chrome-build
ext_chrome_js_files := $(addprefix $(ext_chrome_build_dir)/, $(notdir $(ts_files:ts=js)))
ext_chrome_manifest := $(ext_chrome_build_dir)/manifest.json

dist/quarchive-$(ext_version)-chrome.zip: $(ext_path)/chrome-webextconfig.js $(web_ext) $(ext_chrome_manifest) $(jest_sentinel) $(ext_chrome_js_files) $(html_files) $(icons) $(webextension_polyfill) | dist
	cp $(icons) $(webextension_polyfill) $(html_files) $(ext_chrome_build_dir)
	cd $(ext_path)/; $(realpath $(web_ext)) build -c $(realpath $<)
	mv $(ext_chrome_build_dir)/quarchive-$(ext_version).zip $@

$(ext_chrome_js_files): $(ext_path)/tsconfig-chrome.json $(ts_files) $(tsc) | $(ext_chrome_build_dir)
	$(tsc) --build $<

$(ext_chrome_manifest): $(generate_manifest) $(ext_version_file) | $(ext_chrome_build_dir)
	$(generate_manifest) chrome $(ext_version) > $@


$(jest_sentinel): $(ext_path)/jest.config.js $(ts_files) $(jest)
#	$(jest) -c $<
	touch $@

# $(ext_path)/.eslint-sentinel: $(eslint) $(js_files)
# 	$(eslint) -f unix $(ext_path)/quarchive-background.js $(ext_path)/quarchive-options.js
# 	touch $@

$(web_ext) $(tsc) $(eslint) $(jest) $(webextension_polyfill):
	cd $(ext_path); npm install

dist $(ext_firefox_build_dir) $(ext_chrome_build_dir):
	mkdir -p $@

build: dist/quarchive-$(ext_version)-firefox.zip dist/$(artefact)
