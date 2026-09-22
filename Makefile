.PHONY: help build up down restart logs shell db-shell migrate makemigration seed-admin seed-data test clean

help:
	@echo "ShopEasy — local dev commands"
	@echo ""
	@echo "  make build           Build the Docker images"
	@echo "  make up              Start db + web (runs migrations automatically)"
	@echo "  make down            Stop and remove containers"
	@echo "  make restart         Restart the web container"
	@echo "  make logs            Follow web container logs"
	@echo "  make shell           Open a shell inside the running web container"
	@echo "  make db-shell        Open a psql shell against the dev database"
	@echo "  make migrate         Apply pending migrations (flask db upgrade)"
	@echo "  make makemigration m=\"message\"   Autogenerate a new migration"
	@echo "  make seed-admin      Create the admin user (prompts for password)"
	@echo "  make seed-data       Load sample categories/subcategories/products"
	@echo "  make test            Run the pytest suite (inside a container)"
	@echo "  make clean           Stop containers and remove volumes (DESTROYS local data)"

build:
	docker compose build

up:
	docker compose up -d db
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

db-shell:
	docker compose exec db psql -U ecom_user -d ecom_db

migrate:
	docker compose exec web flask db upgrade

makemigration:
	docker compose exec web flask db migrate -m "$(m)"

seed-admin:
	docker compose exec web flask seed-admin --email admin@example.com

seed-data:
	docker compose exec web flask seed-data

test:
	docker compose run --rm web pytest -q

clean:
	docker compose down -v
