web_ext := src/extension/node_modules/web-ext/bin/web-ext

dist/quartermarker-0.1.zip: src/extension/manifest.json $(web_ext) src/extension/quartermarker.js | dist
	$(web_ext) build -a dist -s src/extension/ --overwrite-dest

$(web_ext):
	cd src/extension; npm install --save-dev web-ext
dist:
	mkdir -p dist
