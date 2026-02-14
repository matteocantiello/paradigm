#!/usr/bin/env bash
# Download Python package wheels for offline installation inside the sandbox.
#
# Usage:
#   ./docker/cache_packages.sh [output_dir]
#
# Default output: data/packages/
# The directory is mounted read-only at /data/packages/ in the Docker container.
# Agents install from there with:
#   pip install --user --no-index --find-links /data/packages/ <package>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REQUIREMENTS="$SCRIPT_DIR/requirements-cache.txt"
OUTPUT_DIR="${1:-$PROJECT_ROOT/data/packages}"

mkdir -p "$OUTPUT_DIR"

echo "Downloading package wheels to: $OUTPUT_DIR"
echo "Requirements file: $REQUIREMENTS"
echo ""

pip download \
    --dest "$OUTPUT_DIR" \
    --requirement "$REQUIREMENTS" \
    --python-version 3.12 \
    --only-binary=:all: \
    2>&1 | grep -E "^(Collecting|Downloading|Saved|File was)" || true

# Fallback: retry without --only-binary for packages without wheels
pip download \
    --dest "$OUTPUT_DIR" \
    --requirement "$REQUIREMENTS" \
    --python-version 3.12 \
    2>&1 | grep -E "^(Collecting|Downloading|Saved|File was)" || true

WHEEL_COUNT=$(find "$OUTPUT_DIR" -name '*.whl' -o -name '*.tar.gz' | wc -l | tr -d ' ')
echo ""
echo "Done. $WHEEL_COUNT packages cached in $OUTPUT_DIR"
