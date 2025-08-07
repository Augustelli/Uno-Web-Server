.PHONY: run build clean deploy

run:
	python3 -m http.server $(PORT)
run-server:
	python3 src/server.py --port $(PORT) --max-players $(MAX-PLAYERS) --turn-timeout $(TURN-TIMEOUT)
run-client:
	python3 src/client.py --host $(HOST) --port $(PORT)
build:
	python3 -m build

setup:
	python3 -m venv .venv
	. .venv/bin/activate
	python3 -m pip install --upgrade pip

clean:
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .venv/



PORT?= 8000
MAX-PLAYERS?= 2
TURN-TIMEOUT?= 15
HOST?=127.0.0.1


