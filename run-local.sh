#!/usr/bin/env bash
set -Eeuo pipefail
DATAPULSE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DATAPULSE_ROOT/frontend/tools/run-local.sh" "$@"
