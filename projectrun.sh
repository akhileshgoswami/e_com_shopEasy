#!/usr/bin/env bash
# One-file local runner for the ShopEasy Flask app.
#
# Usage:
#   ./projectrun.sh              start Datastore emulator + web (build if needed)
#   ./projectrun.sh stop         stop containers
#   ./projectrun.sh restart      restart the web container
#   ./projectrun.sh logs         follow web logs
#   ./projectrun.sh seed-admin   create admin user (prompts for email/password)
#   ./projectrun.sh seed-data    load sample catalog data
#   ./projectrun.sh test         run the pytest suite (against its own emulator)
#   ./projectrun.sh deploy       deploy to Cloud Run (see scripts/deploy.sh)
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
    docker compose up -d datastore
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

  seed-admin)
    read -r -p "Admin email: " ADMIN_EMAIL
    docker compose exec web flask seed-admin --email "$ADMIN_EMAIL"
    ;;

  seed-data)
    docker compose exec web flask seed-data
    ;;

  test)
    docker compose --profile test up -d --wait datastore-test
    docker compose run --rm --no-deps \
      -e DATASTORE_EMULATOR_HOST=datastore-test:8081 -e DATASTORE_PROJECT_ID=e-com-test \
      web pytest -q
    ;;

  deploy)
    shift
    ./scripts/deploy.sh "$@"
    ;;

  shell)
    docker compose exec web bash
    ;;

  reset)
    read -r -p "This deletes the local database and uploaded files. Continue? [y/N] " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
      docker compose --profile test down -v
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
