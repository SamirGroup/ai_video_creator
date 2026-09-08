#!/usr/bin/env bash
#
# deploy.sh — zero-downtime-ish deploy for a single VPS/Cloud VM (SPEC A-25).
#
# Strategy:
#   1. Pull latest code for the given git ref.
#   2. Build new images tagged with the git SHA (kept alongside the previous
#      image so we can roll back instantly without rebuilding).
#   3. Run database migrations BEFORE swapping containers (migrations must be
#      backward-compatible per NFR-39, so the old containers keep working
#      while migrations apply).
#   4. Recreate backend/worker/beat/frontend containers one at a time
#      (`--no-deps`) so db/redis are never restarted during app deploys.
#   5. Health-check the new backend container; on failure, roll back to the
#      previous known-good image tag automatically.
#
# Usage (run from the repo root on the VPS):
#   ./deploy/deploy.sh [git-ref]         # default ref: main
#   ./deploy/deploy.sh --rollback        # redeploy the last known-good tag
#
# Requires: docker, docker compose v2, git. Run as the deploy user (non-root),
# with that user in the `docker` group.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
STATE_DIR="$REPO_DIR/deploy/.state"
LAST_GOOD_FILE="$STATE_DIR/last_good_sha"
HEALTH_URL="http://localhost:8000/api/health/"
HEALTH_RETRIES=10
HEALTH_DELAY=5

mkdir -p "$STATE_DIR"

log() { printf '\n[deploy] %s\n' "$*"; }

rollback() {
  local target_sha="$1"
  log "Rolling back to ${target_sha}..."
  git checkout "$target_sha"
  IMAGE_TAG="$target_sha" $COMPOSE up -d --no-deps backend celery_worker celery_beat frontend
  log "Rollback to ${target_sha} complete."
  exit 1
}

health_check() {
  for i in $(seq 1 "$HEALTH_RETRIES"); do
    if curl -fsS "$HEALTH_URL" > /dev/null 2>&1; then
      log "Health check passed (attempt $i)."
      return 0
    fi
    log "Health check attempt $i/$HEALTH_RETRIES failed, retrying in ${HEALTH_DELAY}s..."
    sleep "$HEALTH_DELAY"
  done
  return 1
}

if [ "${1:-}" = "--rollback" ]; then
  if [ ! -f "$LAST_GOOD_FILE" ]; then
    echo "No previous known-good SHA recorded in $LAST_GOOD_FILE" >&2
    exit 1
  fi
  rollback "$(cat "$LAST_GOOD_FILE")"
fi

GIT_REF="${1:-main}"
PREVIOUS_SHA="$(git rev-parse HEAD)"

log "Fetching latest code (ref: ${GIT_REF})..."
git fetch --all --tags
git checkout "$GIT_REF"
git pull --ff-only

NEW_SHA="$(git rev-parse --short HEAD)"
export IMAGE_TAG="$NEW_SHA"

log "Building images for ${NEW_SHA}..."
$COMPOSE build backend celery_worker celery_beat frontend

log "Applying database migrations (one-off container, before swapping traffic)..."
$COMPOSE run --rm migrate

log "Ensuring infra services (db, redis) are up..."
$COMPOSE up -d db redis

log "Recreating backend..."
$COMPOSE up -d --no-deps backend

if ! health_check; then
  log "New backend failed health check — rolling back to ${PREVIOUS_SHA}."
  rollback "$PREVIOUS_SHA"
fi

log "Recreating celery_worker, celery_beat, frontend..."
$COMPOSE up -d --no-deps celery_worker celery_beat frontend

echo "$NEW_SHA" > "$LAST_GOOD_FILE"
log "Deploy of ${NEW_SHA} succeeded (previous good: ${PREVIOUS_SHA})."

log "Pruning dangling images..."
docker image prune -f > /dev/null || true

log "Done."
