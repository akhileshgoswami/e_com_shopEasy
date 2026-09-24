.PHONY: help build up down restart logs shell seed-admin seed-data test deploy clean

help:
	@echo "ShopEasy — local dev commands"
	@echo ""
	@echo "  make build           Build the Docker images"
	@echo "  make up              Start the Datastore emulator + web"
	@echo "  make down            Stop and remove containers"
	@echo "  make restart         Restart the web container"
	@echo "  make logs            Follow web container logs"
	@echo "  make shell           Open a shell inside the running web container"
	@echo "  make seed-admin      Create the admin user (prompts for password)"
	@echo "  make seed-data       Load sample categories/subcategories/products"
	@echo "  make test            Run the pytest suite (inside a container, own emulator)"
	@echo "  make deploy          Deploy to Cloud Run (scripts/deploy.sh)"
	@echo "  make clean           Stop containers and remove volumes (DESTROYS local data)"

build:
	docker compose build

up:
	docker compose up -d datastore
	docker compose up -d web
	@echo "App running at http://localhost:8000"

down:
	docker compose down

restart:
	docker compose restart web

logs:
	docker compose logs -f web

shell:
	docker compose exec web bash

seed-admin:
	docker compose exec web flask seed-admin --email admin@example.com

seed-data:
	docker compose exec web flask seed-data

test:
	docker compose --profile test up -d --wait datastore-test
	docker compose run --rm --no-deps -e DATASTORE_EMULATOR_HOST=datastore-test:8081 -e DATASTORE_PROJECT_ID=e-com-test web pytest -q

deploy:
	./scripts/deploy.sh

clean:
	docker compose --profile test down -v
