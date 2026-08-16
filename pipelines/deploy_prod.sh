#!/usr/bin/env bash

# Deploy sisimcp on its Ubuntu production host.
#
# This script is intentionally run on the server (normally from /tmp so it can
# deploy the commit that first adds the script). It only accepts a fast-forward
# from the known production baseline, builds before downtime, takes a consistent
# SQLite backup, migrates/fits the detector, recreates the application containers,
# and verifies the public listeners.

set -Eeuo pipefail
IFS=$'\n\t'

readonly EXPECTED_PROD_COMMIT_DEFAULT="9a29aab96ca770b7a7527ce8d13b2a345a061aac"
readonly APP_SERVICES=(mcp_server dify_api_server frontend_nextjs)

REPO_DIR=""
REMOTE="origin"
TARGET_REF=""
EXPECTED_CURRENT="$EXPECTED_PROD_COMMIT_DEFAULT"
ALLOW_CURRENT_MISMATCH=0
SKIP_FIT=0
SYNC_FROM=""
SYNC_TO=""
DEPLOY_DIFY=0
PUBLISH_DIFY=0

DOWNTIME_STARTED=0
NEW_DEPLOYMENT_ATTEMPTED=0
DB_MUTATION_STARTED=0
DB_BACKUP=""
COMPOSE=()

usage() {
    cat <<'EOF'
Usage:
  bash deploy_prod.sh --repo-dir /opt/sisimcp --target <commit-or-tag> [options]

Required:
  --repo-dir PATH       Production sisimcp checkout.
  --target REF          Exact commit/tag to deploy. A commit SHA is recommended.

Options:
  --remote NAME         Git remote to fetch (default: origin).
  --expected-current SHA
                        Required current production commit (default: 9a29aab...).
  --allow-current-mismatch
                        Permit deployment from another current commit. The target
                        must still be a fast-forward.
  --skip-fit            Do not fit rolling-percentile parameters after migration.
  --sync-from DATE      After the app is healthy, backfill BCI data from YYYY-MM-DD
                        and refit. Omit to leave source data unchanged.
  --sync-to DATE        End of BCI backfill (default: current server date).
  --deploy-dify         Back up and update the Dify draft and custom tool schemas.
                        Requires DIFY admin/workspace/app settings in the service env.
  --publish-dify        Also publish the Dify workflow; implies --deploy-dify.
  -h, --help            Show this help.

Example:
  bash /tmp/deploy_prod.sh \
    --repo-dir /opt/sisimcp \
    --target 0123456789abcdef0123456789abcdef01234567

The Dify platform itself is not upgraded by this script. The checked-out submodule
is synchronized, but Dify's own Docker stack and database remain untouched.
EOF
}

log() {
    printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    log "ERROR: $*"
    if (( DOWNTIME_STARTED == 1 || NEW_DEPLOYMENT_ATTEMPTED == 1 )); then
        show_failure_context 1
    fi
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

validate_date() {
    local value="$1"
    [[ "$value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
        || die "Invalid date '$value'; expected YYYY-MM-DD"
    date -d "$value" '+%F' >/dev/null 2>&1 \
        || die "Invalid calendar date: $value"
}

compose() {
    "${COMPOSE[@]}" "$@"
}

show_failure_context() {
    local exit_code="$1"
    set +e

    log "Deployment failed (exit $exit_code)."

    if (( DOWNTIME_STARTED == 1 && NEW_DEPLOYMENT_ATTEMPTED == 0 )); then
        log "Failure happened before container replacement; restoring the database and old containers."
        compose stop -t 20 "${APP_SERVICES[@]}" >/dev/null 2>&1
        if (( DB_MUTATION_STARTED == 1 )) && [[ -n "$DB_BACKUP" && -f "$DB_BACKUP" ]]; then
            cp --preserve=mode,timestamps "$DB_BACKUP" "$REPO_DIR/data/sisi.sqlite"
            log "Restored SQLite from $DB_BACKUP"
        fi
        compose start "${APP_SERVICES[@]}" >/dev/null 2>&1
    elif (( NEW_DEPLOYMENT_ATTEMPTED == 1 )); then
        log "New containers were already attempted; no automatic data rollback was made because production may have accepted writes."
        log "Inspect with: cd '$REPO_DIR/docker' && docker compose logs --tail=200"
    fi

    if [[ -n "$DB_BACKUP" ]]; then
        log "SQLite recovery backup: $DB_BACKUP"
    fi
    compose ps 2>/dev/null || true
    exit "$exit_code"
}

trap 'show_failure_context $?' ERR
trap 'show_failure_context 130' INT
trap 'show_failure_context 143' TERM

while (( $# > 0 )); do
    case "$1" in
        --repo-dir)
            [[ $# -ge 2 ]] || die "--repo-dir requires a value"
            REPO_DIR="$2"
            shift 2
            ;;
        --target)
            [[ $# -ge 2 ]] || die "--target requires a value"
            TARGET_REF="$2"
            shift 2
            ;;
        --remote)
            [[ $# -ge 2 ]] || die "--remote requires a value"
            REMOTE="$2"
            shift 2
            ;;
        --expected-current)
            [[ $# -ge 2 ]] || die "--expected-current requires a value"
            EXPECTED_CURRENT="$2"
            shift 2
            ;;
        --allow-current-mismatch)
            ALLOW_CURRENT_MISMATCH=1
            shift
            ;;
        --skip-fit)
            SKIP_FIT=1
            shift
            ;;
        --sync-from)
            [[ $# -ge 2 ]] || die "--sync-from requires a value"
            SYNC_FROM="$2"
            shift 2
            ;;
        --sync-to)
            [[ $# -ge 2 ]] || die "--sync-to requires a value"
            SYNC_TO="$2"
            shift 2
            ;;
        --deploy-dify)
            DEPLOY_DIFY=1
            shift
            ;;
        --publish-dify)
            DEPLOY_DIFY=1
            PUBLISH_DIFY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$REPO_DIR" ]] || die "--repo-dir is required"
[[ -n "$TARGET_REF" ]] || die "--target is required; deploy a reviewed, immutable commit"
[[ -d "$REPO_DIR/.git" ]] || die "Not a Git checkout: $REPO_DIR"

REPO_DIR="$(cd "$REPO_DIR" && pwd -P)"
readonly COMPOSE_FILE="$REPO_DIR/docker/docker-compose.yml"
readonly DB_FILE="$REPO_DIR/data/sisi.sqlite"

require_command git
require_command docker
require_command curl
require_command date
require_command flock

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    [[ "${ID:-}" == "ubuntu" || " ${ID_LIKE:-} " == *" ubuntu " || " ${ID_LIKE:-} " == *" debian "* ]] \
        || die "This deployment script is intended for Ubuntu/Debian; detected ${PRETTY_NAME:-unknown}"
fi

docker compose version >/dev/null
docker info >/dev/null
[[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"
[[ -f "$REPO_DIR/.env" ]] || die "Production environment file is missing: $REPO_DIR/.env"
[[ -f "$DB_FILE" ]] || die "Production database is missing: $DB_FILE"

if [[ -n "$SYNC_FROM" ]]; then
    validate_date "$SYNC_FROM"
    SYNC_TO="${SYNC_TO:-$(date '+%F')}"
    validate_date "$SYNC_TO"
    [[ "$SYNC_FROM" < "$SYNC_TO" || "$SYNC_FROM" == "$SYNC_TO" ]] \
        || die "--sync-from must not be later than --sync-to"
elif [[ -n "$SYNC_TO" ]]; then
    die "--sync-to requires --sync-from"
fi

COMPOSE=(docker compose --project-directory "$REPO_DIR/docker" -f "$COMPOSE_FILE")
cd "$REPO_DIR"

mkdir -p "$REPO_DIR/data/backups/deploy"
exec 9>"$REPO_DIR/data/backups/deploy/.deploy.lock"
flock -n 9 || die "Another sisimcp deployment is already running"

compose config --quiet
docker network inspect sisi-dify-platform_default >/dev/null \
    || die "Required Docker network does not exist: sisi-dify-platform_default"

for service in "${APP_SERVICES[@]}"; do
    container_id="$(compose ps -q "$service")"
    [[ -n "$container_id" ]] || die "Production service has no existing container: $service"
    [[ "$(docker inspect --format '{{.State.Running}}' "$container_id")" == "true" ]] \
        || die "Production service is not running before deployment: $service"
done

status="$(git status --porcelain --untracked-files=all --ignore-submodules=none)"
[[ -z "$status" ]] || {
    printf '%s\n' "$status" >&2
    die "Production checkout has local changes; preserve or remove them before deploying"
}

current_commit="$(git rev-parse HEAD)"
log "Current production commit: $current_commit"

git fetch --prune "$REMOTE"
target_commit="$(git rev-parse --verify "${TARGET_REF}^{commit}")" \
    || die "Target is not a commit after fetching $REMOTE: $TARGET_REF"
log "Resolved deployment target: $target_commit"

if (( ALLOW_CURRENT_MISMATCH == 0 )) \
    && [[ "$current_commit" != "$EXPECTED_CURRENT" ]] \
    && [[ "$current_commit" != "$target_commit" ]]; then
    die "Expected production at $EXPECTED_CURRENT, found $current_commit (use --allow-current-mismatch only after review)"
fi

git merge-base --is-ancestor "$current_commit" "$target_commit" \
    || die "Target $target_commit is not a fast-forward from $current_commit"

if [[ "$current_commit" != "$target_commit" ]]; then
    log "Fast-forwarding the production checkout"
    git merge --ff-only "$target_commit"
else
    log "Checkout is already at the requested target; continuing idempotently"
fi

git submodule sync -- dify
git submodule update --init --recursive --jobs 4 dify

[[ -z "$(git status --porcelain --untracked-files=all --ignore-submodules=none)" ]] \
    || die "Checkout is not clean after updating source and submodules"
[[ "$(git rev-parse HEAD)" == "$target_commit" ]] \
    || die "Checkout did not reach the requested target"

if grep -Eq '^[[:space:]]*DIFY_CHATFLOW_URL=.*localhost:8080' "$REPO_DIR/.env"; then
    log "WARNING: .env still points DIFY_CHATFLOW_URL at localhost:8080; the current template uses port 7080. Verify the production-specific URL."
fi

log "Building application images while the old containers remain online"
compose build "${APP_SERVICES[@]}"

log "Running the schema migration regression tests in the new backend image"
compose run --rm --no-deps dify_api_server \
    uv run pytest -q tests/mcp_conductor/entry/test_main_setup_schema.py

timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
backup_rel="backups/deploy/sisi-${timestamp}-${current_commit:0:12}.sqlite"
DB_BACKUP="$REPO_DIR/data/$backup_rel"

log "Creating a consistent SQLite backup before downtime"
compose run --rm --no-deps dify_api_server python -c \
    'import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' \
    /app/data/sisi.sqlite "/app/data/$backup_rel"
compose run --rm --no-deps dify_api_server python -c \
    'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); result=c.execute("PRAGMA integrity_check").fetchone()[0]; c.close(); print(result); raise SystemExit(0 if result == "ok" else 1)' \
    "/app/data/$backup_rel"
[[ -s "$DB_BACKUP" ]] || die "SQLite backup was not created: $DB_BACKUP"

log "Stopping application containers for the schema migration"
DOWNTIME_STARTED=1
compose stop -t 30 "${APP_SERVICES[@]}"
DB_MUTATION_STARTED=1

log "Applying the idempotent SQLite schema migration"
compose run --rm --no-deps dify_api_server \
    uv run python -m mcp_conductor.entry.main_setup_schema

if (( SKIP_FIT == 0 )); then
    log "Validating detector fitting without writes"
    compose run --rm --no-deps dify_api_server \
        uv run python -m mcp_conductor.entry.main_fit_model --dry_run
    log "Persisting detector parameters"
    compose run --rm --no-deps dify_api_server \
        uv run python -m mcp_conductor.entry.main_fit_model
fi

log "Starting the new application containers"
NEW_DEPLOYMENT_ATTEMPTED=1
compose up -d --no-build --force-recreate "${APP_SERVICES[@]}"

wait_for_http() {
    local name="$1"
    local url="$2"
    local require_success="$3"
    local deadline=$((SECONDS + 120))
    local code="000"

    while (( SECONDS < deadline )); do
        code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
            --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || true)"
        if [[ "$require_success" == "yes" && "$code" =~ ^2[0-9][0-9]$ ]]; then
            log "$name is healthy ($code)"
            return 0
        fi
        if [[ "$require_success" == "no" && "$code" != "000" && "$code" -lt 500 ]]; then
            log "$name is responding ($code)"
            return 0
        fi
        sleep 3
    done

    log "$name did not become healthy at $url (last HTTP code: $code)"
    compose logs --tail=120 "$name" || true
    return 1
}

wait_for_http dify_api_server http://127.0.0.1:8002/health yes
wait_for_http frontend_nextjs http://127.0.0.1:3001/ yes
wait_for_http mcp_server http://127.0.0.1:8010/mcp no

for service in "${APP_SERVICES[@]}"; do
    container_id="$(compose ps -q "$service")"
    [[ -n "$container_id" && "$(docker inspect --format '{{.State.Running}}' "$container_id")" == "true" ]] \
        || die "Container is not running after deployment: $service"
done

if [[ -n "$SYNC_FROM" ]]; then
    log "Backfilling BCI data from $SYNC_FROM through $SYNC_TO while the app remains online"
    compose run --rm --no-deps dify_api_server \
        uv run python -m mcp_conductor.entry.main_sync_bci_data \
        --start-date "$SYNC_FROM" --end-date "$SYNC_TO"

    if (( SKIP_FIT == 0 )); then
        log "Refitting detector parameters after the BCI backfill"
        compose run --rm --no-deps dify_api_server \
            uv run python -m mcp_conductor.entry.main_fit_model --dry_run
        compose run --rm --no-deps dify_api_server \
            uv run python -m mcp_conductor.entry.main_fit_model
    fi
fi

if (( DEPLOY_DIFY == 1 )); then
    log "Deploying the Dify workflow draft and custom tool schemas with remote backups"
    dify_args=(--apply)
    if (( PUBLISH_DIFY == 1 )); then
        dify_args+=(--publish)
    fi
    compose run --rm --no-deps dify_api_server \
        uv run python -m mcp_conductor.entry.main_deploy_dify_workflow "${dify_args[@]}"
fi

log "Verifying the migrated database from the live API container"
compose exec -T dify_api_server python -c \
    'import sqlite3; c=sqlite3.connect("/app/data/sisi.sqlite"); required={"m_roll_percentile_parameter","m_roll_percentile_monitor"}; tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")}; cols={r[1] for r in c.execute("PRAGMA table_info(ship_cnt_in_pipe)")}; count=c.execute("SELECT COUNT(*) FROM m_roll_percentile_parameter").fetchone()[0]; c.close(); print(f"parameter_rows={count}"); raise SystemExit(0 if required <= tables and "duration" in cols else 1)'

compose ps
trap - ERR INT TERM

log "Deployment complete: $current_commit -> $target_commit"
log "SQLite backup: $DB_BACKUP"
if (( DEPLOY_DIFY == 0 )); then
    log "Dify workflow/tool files were not applied (use --deploy-dify or --publish-dify when its admin API is configured)."
fi
if [[ -z "$SYNC_FROM" ]]; then
    log "BCI history was not backfilled. Use --sync-from on a later idempotent run if production lacks duration/port history."
fi
