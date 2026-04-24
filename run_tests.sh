#!/bin/bash
#
# PGWarden Test Suite
# Starts a temporary TimescaleDB, runs all tests, generates reports, cleans up.
#
# Usage: ./run_tests.sh

set -e

TEST_DB_PORT="5437"

export DB_HOST="localhost"
export DB_PORT="$TEST_DB_PORT"
export DB_USER="postgres"
export DB_PASSWORD="postgres"
export TEST_DB_NAME="pgwarden_test"
export DB_NAME="pgwarden_test"
export PGWARDEN_EMAIL="admin@pgwarden.io"
export PGWARDEN_PASSWORD="admin"
export IS_TESTING="1"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m'

cleanup() {
  echo ""
  echo -e "${YELLOW}Cleaning up...${NC}"
  docker compose -f docker-compose.test.yaml down 2>/dev/null || true
  rm -rf migrations/.venv.test api/.venv.test
  echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  PGWarden Test Suite${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}[1/5] Starting test database on port $TEST_DB_PORT...${NC}"
docker compose -f docker-compose.test.yaml up -d --wait
echo -e "${GREEN}Database is ready.${NC}"
echo ""

mkdir -p test-results

echo -e "${YELLOW}[2/5] Creating isolated test environments...${NC}"
UV_PROJECT_ENVIRONMENT=.venv.test uv sync --directory migrations --quiet
UV_PROJECT_ENVIRONMENT=.venv.test uv sync --directory api --quiet
echo -e "${GREEN}Environments ready.${NC}"
echo ""

echo -e "${YELLOW}[3/5] Running migration tests...${NC}"
cd migrations
UV_PROJECT_ENVIRONMENT=.venv.test uv run pytest tests/ \
  --junitxml=../test-results/migration-report.xml \
  --html=../test-results/migration-report.html \
  --self-contained-html -v
MIGRATION_EXIT=$?
cd ..

if [ $MIGRATION_EXIT -eq 0 ]; then
  echo -e "${GREEN}Migration tests PASSED.${NC}"
else
  echo -e "${RED}Migration tests FAILED.${NC}"
fi
echo ""

echo -e "${YELLOW}[4/5] Running API tests...${NC}"
cd api
PYTHONPATH="." UV_PROJECT_ENVIRONMENT=.venv.test uv run pytest tests/ \
  --junitxml=../test-results/api-report.xml \
  --html=../test-results/api-report.html \
  --self-contained-html -v
API_EXIT=$?
cd ..

if [ $API_EXIT -eq 0 ]; then
  echo -e "${GREEN}API tests PASSED.${NC}"
else
  echo -e "${RED}API tests FAILED.${NC}"
fi
echo ""

echo -e "${YELLOW}[5/5] Stopping test database...${NC}"
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Results${NC}"
echo -e "${CYAN}========================================${NC}"

if [ $MIGRATION_EXIT -eq 0 ]; then
  echo -e "  Migrations: ${GREEN}PASSED${NC}"
else
  echo -e "  Migrations: ${RED}FAILED${NC}"
fi

if [ $API_EXIT -eq 0 ]; then
  echo -e "  API:        ${GREEN}PASSED${NC}"
else
  echo -e "  API:        ${RED}FAILED${NC}"
fi

echo ""
echo -e "  Reports: ${GRAY}test-results/${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

if [ $MIGRATION_EXIT -ne 0 ] || [ $API_EXIT -ne 0 ]; then
  exit 1
fi
