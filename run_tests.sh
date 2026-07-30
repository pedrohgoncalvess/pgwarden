#!/bin/bash
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

TEST_DB_PORT="5437"
WORKSPACE_VENV="$PROJECT_ROOT/.venv.test"
LOCAL_UV_DIR="$PROJECT_ROOT/.tools/uv"

export DB_HOST="localhost"
export DB_PORT="$TEST_DB_PORT"
export DB_USER="postgres"
export DB_PASSWORD="postgres"
export TEST_DB_NAME="postgres"
export DB_NAME="postgres"
export PGWARDEN_EMAIL="admin@pgwarden.io"
export PGWARDEN_PASSWORD="admin"
export IS_TESTING="1"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m'

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_CMD="$(command -v uv)"
    return
  fi

  if [ -x "$LOCAL_UV_DIR/uv" ]; then
    UV_CMD="$LOCAL_UV_DIR/uv"
    return
  fi

  echo -e "${YELLOW}uv was not found; installing it into ${LOCAL_UV_DIR}...${NC}"
  mkdir -p "$LOCAL_UV_DIR"

  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh |
      env UV_INSTALL_DIR="$LOCAL_UV_DIR" UV_NO_MODIFY_PATH=1 sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh |
      env UV_INSTALL_DIR="$LOCAL_UV_DIR" UV_NO_MODIFY_PATH=1 sh
  else
    echo -e "${RED}Cannot install uv: curl or wget is required.${NC}"
    exit 1
  fi

  if [ ! -x "$LOCAL_UV_DIR/uv" ]; then
    echo -e "${RED}uv installation did not produce ${LOCAL_UV_DIR}/uv.${NC}"
    exit 1
  fi
  UV_CMD="$LOCAL_UV_DIR/uv"
}

sync_api_environment() {
  UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" sync --directory api || return 1

  local api_env="$PROJECT_ROOT/api/.venv.test"
  if "$api_env/bin/python" -c "import cryptography, yoyo" >/dev/null 2>&1; then
    return
  fi

  echo -e "${YELLOW}  API environment is incomplete; rebuilding it once...${NC}"
  case "$api_env" in
    "$PROJECT_ROOT/api/.venv.test")
      rm -rf -- "$api_env"
      ;;
    *)
      echo -e "${RED}Refusing to remove unexpected environment path: ${api_env}${NC}"
      return 1
      ;;
  esac

  UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" sync --directory api || return 1
  "$api_env/bin/python" -c "import cryptography, yoyo"
}

cleanup() {
  echo ""
  echo -e "${YELLOW}Cleaning up test database and volumes...${NC}"
  docker compose -f docker-compose.test.yaml down --volumes --remove-orphans 2>/dev/null || true
  echo -e "${GREEN}Done. Virtual environments were preserved.${NC}"
}
trap cleanup EXIT

print_result() {
  local label="$1"
  local exit_code="$2"
  if [ "$exit_code" -eq 0 ]; then
    echo -e "  ${label}: ${GREEN}PASSED${NC}"
  else
    echo -e "  ${label}: ${RED}FAILED (${exit_code})${NC}"
  fi
}

ensure_uv
export UV_CACHE_DIR="$PROJECT_ROOT/.uv-cache"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  PGWarden Test Suite${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}[1/10] Starting test database on port $TEST_DB_PORT...${NC}"
docker compose -f docker-compose.test.yaml up -d --wait || exit 1
echo -e "${GREEN}Database is ready.${NC}"
echo ""

mkdir -p test-results

echo -e "${YELLOW}[2/10] Syncing isolated test environments...${NC}"
echo -e "${GRAY}  Syncing migrations dependencies...${NC}"
UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" sync --directory migrations || exit 1
echo -e "${GRAY}  Syncing API dependencies...${NC}"
sync_api_environment || exit 1
echo -e "${GRAY}  Syncing analytics and notifier dependencies...${NC}"
UV_PROJECT_ENVIRONMENT="$WORKSPACE_VENV" "$UV_CMD" sync --all-packages || exit 1
echo -e "${GRAY}  Syncing collector dependencies...${NC}"
UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" sync --directory collector || exit 1
if [ ! -x "$PROJECT_ROOT/frontend/node_modules/.bin/vitest" ]; then
  echo -e "${GRAY}  Installing frontend dependencies...${NC}"
  npm ci --prefix frontend || exit 1
else
  echo -e "${GRAY}  Frontend dependencies are already installed.${NC}"
fi
echo -e "${GREEN}Environments ready.${NC}"
echo ""

echo -e "${YELLOW}[3/10] Running migration tests...${NC}"
(
  cd migrations
  UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" run pytest tests/ \
    --html=../test-results/migration-report.html \
    --self-contained-html -v
)
MIGRATION_EXIT=$?
echo ""

echo -e "${YELLOW}[4/10] Running API tests...${NC}"
(
  cd api
  PYTHONPATH="." UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" run pytest tests/ \
    --html=../test-results/api-report.html \
    --self-contained-html -v
)
API_EXIT=$?
echo ""

echo -e "${YELLOW}[5/10] Running analytics tests...${NC}"
(
  cd analytics
  PYTHONPATH=".." UV_PROJECT_ENVIRONMENT="$WORKSPACE_VENV" "$UV_CMD" run pytest tests/ -v
)
ANALYTICS_EXIT=$?
echo ""

echo -e "${YELLOW}[6/10] Running notifier tests...${NC}"
(
  cd notifier
  PYTHONPATH=".." UV_PROJECT_ENVIRONMENT="$WORKSPACE_VENV" "$UV_CMD" run pytest tests/ -v
)
NOTIFIER_EXIT=$?
echo ""

echo -e "${YELLOW}[7/10] Running collector tests...${NC}"
(
  cd collector
  PYTHONPATH="." UV_PROJECT_ENVIRONMENT=.venv.test "$UV_CMD" run pytest tests/ -v
)
COLLECTOR_EXIT=$?
echo ""

echo -e "${YELLOW}[8/10] Running frontend unit tests...${NC}"
(
  cd frontend
  npm run test
)
FRONTEND_TEST_EXIT=$?
echo ""

echo -e "${YELLOW}[9/10] Running frontend compile and type checks...${NC}"
(
  cd frontend
  npm run check
)
FRONTEND_CHECK_EXIT=$?
echo ""

echo -e "${YELLOW}[10/10] Summarizing results...${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Results${NC}"
echo -e "${CYAN}========================================${NC}"
print_result "Migrations" "$MIGRATION_EXIT"
print_result "API       " "$API_EXIT"
print_result "Analytics " "$ANALYTICS_EXIT"
print_result "Notifier  " "$NOTIFIER_EXIT"
print_result "Collector " "$COLLECTOR_EXIT"
print_result "Frontend tests" "$FRONTEND_TEST_EXIT"
print_result "Frontend check" "$FRONTEND_CHECK_EXIT"
echo ""
echo -e "  HTML reports: ${GRAY}test-results/${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

if [ "$MIGRATION_EXIT" -ne 0 ] ||
   [ "$API_EXIT" -ne 0 ] ||
   [ "$ANALYTICS_EXIT" -ne 0 ] ||
   [ "$NOTIFIER_EXIT" -ne 0 ] ||
   [ "$COLLECTOR_EXIT" -ne 0 ] ||
   [ "$FRONTEND_TEST_EXIT" -ne 0 ] ||
   [ "$FRONTEND_CHECK_EXIT" -ne 0 ]; then
  exit 1
fi
