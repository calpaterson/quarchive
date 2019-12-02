dist/quartermarker-0.1.zip: src/extension/manifest.json | dist
	src/extension/node_modules/web-ext/bin/web-ext build -a dist -s src/extension/ --overwrite-dest

dist:
	mkdir dist

