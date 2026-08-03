.PHONY: install test dev

install:
	python -m pip install -e "server[dev]"
	cd cli && npm install

test:
	python -m pytest server/tests -q
	cd cli && npm test

dev:
	cd server && uvicorn kl_server.main:app --reload --port 8700 &
	cd cli && npm run tui
