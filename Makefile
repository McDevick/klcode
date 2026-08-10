.PHONY: install ci test dev

install:
	python -m pip install -e "server[dev]"
	cd cli && npm install

ci:
	python -m pip install -e "server[dev]"
	cd cli && npm ci

test:
	python -m pytest server/tests -q
	cd cli && npm test

dev:
	cd cli && npm run tui
