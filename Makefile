web_ext := src/extension/node_modules/web-ext/bin/web-ext

.PHONY: build

build: dist/quartermarker-0.1.zip dist/quartermarker-0.0.1.pex

dist/quartermarker-0.0.1.pex: src/server src/server/quartermarker/__init__.py | dist
	cd src/server; tox
	mv src/server/dist/quartermarker-0.0.1.pex dist/

dist/quartermarker-0.1.zip: src/extension/ $(web_ext) src/extension/quartermarker.js | dist
	$(web_ext) build -a dist -s src/extension/ --overwrite-dest

$(web_ext):
	cd src/extension; npm install --save-dev web-ext
dist:
	mkdir -p dist
