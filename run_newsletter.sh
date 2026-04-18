#!/bin/bash
# Run from project directory; loads .env then executes newsletter script.
set -euo pipefail
cd "$(dirname "$0")"
export $(grep -v '^#' .env | xargs)
python3 arxiv_newsletter.py
