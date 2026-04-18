#!/bin/bash
# Local test runner — production runs via GitHub Actions.
set -euo pipefail
cd "$(dirname "$0")"
export $(grep -v '^#' .env | xargs)
docker compose run newsletter
