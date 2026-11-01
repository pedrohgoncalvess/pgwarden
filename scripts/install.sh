#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash install.sh <full|collector|server> [options]

  full          Complete stack, including the PostgreSQL-backed collector
  collector     SQLite collector and outgoing HTTP sender
  server        Central HTTP receiver, analytics, notifier and frontend

Options:
  --dir PATH        Clone into PATH, or reuse its existing checkout
  --repo URL        Repository to clone (default: official PGWarden repository)
  --ref REF         Branch/tag for a new clone; verified on an existing checkout
  --name NAME       Compose project name (default: pgwarden / pgwarden-local)
  --configure-only  Create missing configuration files without starting services
  -h, --help        Show this help

Requires Bash, Git, Docker Engine and Docker Compose v2. Existing checkouts and
configuration are preserved; upgrades require an explicit git pull/checkout.
EOF
}

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

mode="${1:-}"
case "$mode" in
  -h|--help) usage; exit 0 ;;
  full|collector|server) shift ;;
  *) usage >&2; exit 1 ;;
esac
repo='https://github.com/pedrohgoncalvess/pgwarden.git'
ref=''
name='pgwarden'
[[ "$mode" != collector ]] || name='pgwarden-local'
configure_only=false
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$script_dir/../docker-compose.yaml" && -d "$script_dir/../collector" ]]; then
  destination="$(cd -- "$script_dir/.." && pwd)"
else
  destination="$PWD/pgwarden"
fi
while (($#)); do
  case "$1" in
    --dir|--repo|--ref|--name)
      (($# >= 2)) && [[ -n "$2" ]] || die "Missing value for $1"
      case "$1" in
        --dir) destination="$2" ;;
        --repo) repo="$2" ;;
        --ref) ref="$2" ;;
        --name) name="$2" ;;
      esac
      shift 2 ;;
    --configure-only) configure_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
[[ "$name" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die 'Invalid Compose project name'
for program in git docker; do
  command -v "$program" >/dev/null 2>&1 || die "$program is required"
done
docker compose version >/dev/null 2>&1 || die 'Docker Compose v2 is required'
docker info >/dev/null 2>&1 || die 'Docker Engine is unavailable or access was denied'

if [[ -e "$destination" ]]; then
  [[ -d "$destination" ]] || die "Not a directory: $destination"
  git -C "$destination" rev-parse --show-toplevel >/dev/null 2>&1 || die "Not a Git checkout: $destination"
  [[ -f "$destination/docker-compose.yaml" && -f "$destination/collector/main.py" ]] || die 'Destination is not a PGWarden checkout'
  if [[ -n "$ref" ]]; then
    current="$(git -C "$destination" rev-parse HEAD)"
    expected="$(git -C "$destination" rev-parse --verify "${ref}^{commit}")" || die 'Ref is unavailable locally'
    [[ "$current" == "$expected" ]] || die 'Checkout differs from --ref; switch it explicitly or choose a new --dir'
  fi
else
  clone_args=()
  [[ -z "$ref" ]] || clone_args+=(--branch "$ref")
  git clone "${clone_args[@]}" -- "$repo" "$destination"
fi
cd -- "$destination"
printf 'Using %s (%s)\n' "$PWD" "$mode"

# Generate secrets with Python's standard library inside Docker; no local Python
# or cryptography installation is needed. Files belong to the invoking user.
docker run --rm -i --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD,target=/workspace" \
  --workdir /workspace python:3.13-slim python - "$mode" <<'PY'
import base64
import os
import secrets
import shutil
import sys
from pathlib import Path

os.umask(0o077)
mode = sys.argv[1]
def fernet_key():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

if mode == 'collector':
    env = Path('.env.sqlite')
    if not env.exists():
        template = Path('docker/.env.collector.example').read_text()
        env.write_text(template.replace('replace-with-a-generated-fernet-key', fernet_key()))
        print('Created .env.sqlite; configure SENDER_URL and SENDER_PROJECT_KEY.')
    target = Path('config.sqlite.yaml')
    if not target.exists():
        shutil.copyfile('collector/config.sqlite.example.yaml', target)
        target.chmod(0o600)
        print('Created config.sqlite.yaml; configure monitored PostgreSQL targets.')
else:
    env = Path('.env')
    if not env.exists():
        password = secrets.token_urlsafe(32)
        values = {
            'ENCRYPTION_KEY': fernet_key(), 'JWT_SECRET_KEY': secrets.token_urlsafe(48),
            'PGWARDEN_EMAIL': 'admin@example.com', 'PGWARDEN_PASSWORD': secrets.token_urlsafe(24),
            'DB_USER': 'postgres', 'DB_PASSWORD': password, 'DB_NAME': 'postgres',
            'DB_HOST': 'db', 'DB_PORT': '5432', 'API_PORT': '8080', 'FRONTEND_PORT': '3000',
        }
        if mode == 'full':
            target = Path('config.local.yaml')
            if target.exists():
                raise SystemExit('config.local.yaml already exists; configure .env manually to preserve credentials')
            config = Path('config.yaml').read_text().replace('password: postgres', 'password: ' + password)
            target.write_text(config)
            values['PGWARDEN_CONFIG_FILE'] = './config.local.yaml'
        env.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))
        print('Created .env with generated secrets and administrator credentials; retain this file.')
PY

if "$configure_only"; then
  printf 'Configuration ready in %s. Edit it, then repeat without --configure-only.\n' "$PWD"
  exit 0
fi
case "$mode" in
  full) compose_file='docker-compose.yaml'; env_file='.env' ;;
  server) compose_file='docker/docker-compose.server.yaml'; env_file='.env' ;;
  collector)
    compose_file='docker/docker-compose.collector-sqlite.yaml'; env_file='.env.sqlite'
    if grep -Eq '^(SENDER_URL|SENDER_PROJECT_KEY)=.*(example\.com|replace)' "$env_file" ||
       grep -Eq 'postgres\.internal|replace-with-monitor-password' config.sqlite.yaml; then
      die 'Edit .env.sqlite (receiving URL/project key) and config.sqlite.yaml (targets), then rerun'
    fi ;;
esac
if grep -Eq '^(ENCRYPTION_KEY|JWT_SECRET_KEY|PGWARDEN_PASSWORD)=.*replace-with' "$env_file"; then
  die "Replace placeholder secrets in $env_file before starting"
fi
compose=(docker compose --env-file "$env_file" -p "$name" -f "$compose_file")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
"${compose[@]}" ps
if [[ "$mode" == collector ]]; then
  printf 'Collector and sender started. Follow delivery with:\n'
else
  printf 'Dashboard: http://localhost:<FRONTEND_PORT, default 3000>. Credentials are in .env.\n'
fi
printf 'docker compose --env-file %q -p %q -f %q logs -f\n' "$env_file" "$name" "$compose_file"
