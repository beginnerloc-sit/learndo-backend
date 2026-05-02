#!/bin/bash
# deploy.sh - Pull, install deps, and restart the FastAPI backend
# Usage: ./deploy.sh [--no-pull] [--no-deps] [--reload]

set -e

# --- Config ---
PROJECT_DIR="$HOME/project/learndo-backend"
SERVICE_NAME="learndo-backend"
VENV_PATH="$PROJECT_DIR/venv"
HEALTH_URL="http://127.0.0.1:8000"

# --- Flags ---
DO_PULL=true
DO_DEPS=true
USE_RELOAD=false

for arg in "$@"; do
    case $arg in
        --no-pull) DO_PULL=false ;;
        --no-deps) DO_DEPS=false ;;
        --reload)  USE_RELOAD=true ;;
        -h|--help)
            echo "Usage: $0 [--no-pull] [--no-deps] [--reload]"
            echo ""
            echo "Options:"
            echo "  --no-pull    Skip git pull"
            echo "  --no-deps    Skip pip install"
            echo "  --reload     Use systemctl reload instead of restart (zero-downtime)"
            exit 0
            ;;
    esac
done

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}==>${NC} $1"; }
info() { echo -e "${BLUE}i${NC}  $1"; }
warn() { echo -e "${YELLOW}!${NC}  $1"; }
err()  { echo -e "${RED}✗${NC}  $1"; }

# --- Sanity checks ---
if [ ! -d "$PROJECT_DIR" ]; then
    err "Project directory not found: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR"

if [ ! -d "$VENV_PATH" ]; then
    err "Virtualenv not found at $VENV_PATH"
    echo "Create it with: python3 -m venv venv"
    exit 1
fi

if ! systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
    err "systemd service '$SERVICE_NAME' not found"
    echo "Make sure /etc/systemd/system/${SERVICE_NAME}.service exists"
    exit 1
fi

# --- Show current state ---
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
info "Current commit: $CURRENT_COMMIT"

# --- Git pull ---
if [ "$DO_PULL" = true ]; then
    log "Pulling latest code..."
    if [ -n "$(git status --porcelain)" ]; then
        warn "Uncommitted changes detected:"
        git status --short
        read -p "Continue anyway? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            err "Aborted."
            exit 1
        fi
    fi
    git pull
    NEW_COMMIT=$(git rev-parse --short HEAD)
    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
        info "Already up to date"
    else
        info "Updated: $CURRENT_COMMIT -> $NEW_COMMIT"
    fi
else
    info "Skipping git pull (--no-pull)"
fi

# --- Activate venv ---
# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"

# --- Install dependencies ---
if [ "$DO_DEPS" = true ]; then
    if [ -f "requirements.txt" ]; then
        log "Installing dependencies..."
        pip install -q -r requirements.txt
    else
        warn "No requirements.txt found, skipping pip install"
    fi
else
    info "Skipping dependency install (--no-deps)"
fi

# --- Optional: run database migrations if alembic exists ---
if [ -f "alembic.ini" ]; then
    log "Running database migrations..."
    alembic upgrade head
fi

# --- Restart or reload service ---
if [ "$USE_RELOAD" = true ]; then
    log "Reloading $SERVICE_NAME (zero-downtime)..."
    systemctl reload "$SERVICE_NAME"
else
    log "Restarting $SERVICE_NAME..."
    systemctl restart "$SERVICE_NAME"
fi

# --- Wait briefly and check status ---
sleep 2

if systemctl is-active --quiet "$SERVICE_NAME"; then
    log "Service is running"
else
    err "Service failed to start!"
    echo ""
    echo "--- Recent logs ---"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    exit 1
fi

# --- Health check ---
log "Health check..."
sleep 1
if curl -sf -o /dev/null -m 5 "$HEALTH_URL"; then
    log "Endpoint responding at $HEALTH_URL"
else
    warn "Health check failed (endpoint may not be ready yet)"
    info "Check logs: journalctl -u $SERVICE_NAME -f"
fi

# --- Summary ---
echo ""
log "Deploy complete!"
echo ""
echo "  Service:  $SERVICE_NAME"
echo "  Commit:   $(git rev-parse --short HEAD)"
echo "  Status:   $(systemctl is-active $SERVICE_NAME)"
echo "  Logs:     journalctl -u $SERVICE_NAME -f"
echo ""