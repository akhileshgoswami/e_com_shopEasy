#!/usr/bin/env bash
# One-file local runner for the ShopEasy Flask app.
#
# Usage:
#   ./projectrun.sh              start db + web (build if needed)
#   ./projectrun.sh stop         stop containers
#   ./projectrun.sh restart      restart the web container
#   ./projectrun.sh logs         follow web logs
#   ./projectrun.sh migrate      apply pending migrations
#   ./projectrun.sh makemigration "message"   autogenerate a new migration
#   ./projectrun.sh seed-admin   create admin user (prompts for email/password)
#   ./projectrun.sh seed-data    load sample catalog data
#   ./projectrun.sh test         run the pytest suite
#   ./projectrun.sh shell        shell into the web container
#   ./projectrun.sh reset        stop and wipe all local data (DESTRUCTIVE)

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_URL="http://localhost:8000"
CMD="${1:-start}"

require_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "Docker isn't running. Start Docker Desktop and try again."
    exit 1
  fi
}

wait_for_health() {
  echo -n "Waiting for the app to become healthy"
  for _ in $(seq 1 30); do
    if curl -fsS "${APP_URL}/health" >/dev/null 2>&1; then
      echo ""
      echo "App is up: ${APP_URL}"
      return 0
    fi
    echo -n "."
    sleep 2
  done
  echo ""
  echo "App did not become healthy in time. Check logs with: ./projectrun.sh logs"
  return 1
}

case "$CMD" in
  start|up|"")
    require_docker
    if [ -n "$(docker compose ps -q)" ]; then
      echo "Stopping running containers first..."
      docker compose down
    fi
    docker compose build
    docker compose up -d db
    docker compose up -d web
    wait_for_health || true
    ;;

  stop|down)
    docker compose down
    ;;

  restart)
    docker compose restart web
    ;;

  logs)
    docker compose logs -f web
    ;;

  migrate)
    docker compose exec web flask db upgrade
    ;;

  makemigration)
    MSG="${2:?Usage: ./projectrun.sh makemigration \"description of change\"}"
    docker compose exec web flask db migrate -m "$MSG"
    ;;

  seed-admin)
    read -r -p "Admin email: " ADMIN_EMAIL
    docker compose exec web flask seed-admin --email "$ADMIN_EMAIL"
    ;;

  seed-data)
    docker compose exec web flask seed-data
    ;;

  test)
    docker compose run --rm web pytest -q
    ;;

  shell)
    docker compose exec web bash
    ;;

  db-shell)
    docker compose exec db psql -U ecom_user -d ecom_db
    ;;

  reset)
    read -r -p "This deletes the local database and uploaded files. Continue? [y/N] " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
      docker compose down -v
      echo "Local data wiped."
    else
      echo "Aborted."
    fi
    ;;

  *)
    echo "Unknown command: $CMD"
    echo "Run './projectrun.sh' with no arguments to see usage in the script header."
    exit 1
    ;;
esac
