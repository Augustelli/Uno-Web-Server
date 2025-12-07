.PHONY: run build clean deploy run-server run-client run-docker-server run-docker-client run-docker-db setup

run-server:
	python3 src/server.py

run-client:
	python3 src/client.py

build:
	docker build -f deployment/Dockerfile.server -t uno-server:1 .
	docker build -f deployment/Dockerfile.client -t uno-client:1 .

run-docker-server:
	docker compose -f deployment/docker-compose.yaml up -d

run-docker-client:
	docker run --rm -it --network uno-network -e HOST=server -e PORT=8000 uno-client:1

run-docker-db:
	docker compose -f deployment/docker-compose-db.yaml up -d

stop-docker:
	docker compose -f deployment/docker-compose.yaml down
	docker compose -f deployment/docker-compose-client.yaml down
	docker compose -f deployment/docker-compose-db.yaml down

setup:
	python3 -m venv .venv && . .venv/bin/activate && python3 -m pip install --upgrade pip && \
	pip install -r requirements.txt

clean:
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .venv/