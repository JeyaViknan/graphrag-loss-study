#!/usr/bin/env bash
# E0 — build and freeze the GraphRAG index.
#
# Runs once. Everything downstream reads the artifacts this produces and
# identifies them by the manifest hash, so re-running this invalidates every
# result computed against the previous index.
#
# Usage: scripts/00_index.sh --root <project_root> [--settings settings.yaml]
set -euo pipefail

ROOT="."
SETTINGS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)     ROOT="$2";     shift 2 ;;
    --settings) SETTINGS="$2"; shift 2 ;;
    -h|--help)  sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

SETTINGS="${SETTINGS:-$ROOT/settings.yaml}"
CONFIG_DIR="$ROOT/configs"
OUTPUT_DIR="$ROOT/output"

if [[ ! -f "$SETTINGS" ]]; then
  echo "E0 FAILED: $SETTINGS not found. Run 'graphrag init --root $ROOT' first." >&2
  exit 2
fi

# 1. Freeze the config alongside the index it produced.
mkdir -p "$CONFIG_DIR"
cp "$SETTINGS" "$CONFIG_DIR/frozen_settings.yaml"
echo "E0: froze $SETTINGS -> $CONFIG_DIR/frozen_settings.yaml"

# 2. Build the index.
echo "E0: running graphrag index --root $ROOT"
graphrag index --root "$ROOT"

# 3. Assert all six parquets exist before anything downstream trusts them.
MISSING=0
for f in entities relationships communities community_reports text_units documents; do
  if [[ ! -f "$OUTPUT_DIR/$f.parquet" ]]; then
    echo "E0 FAILED: $OUTPUT_DIR/$f.parquet is missing" >&2
    MISSING=1
  fi
done
[[ "$MISSING" -eq 0 ]] || exit 2

# 4. Generate the manifest covering all six.
python -c "
from pathlib import Path
from graphrag_loss.io import write_manifest, manifest_hash
out = Path('$OUTPUT_DIR')
write_manifest(out)
print(f'E0: manifest hash = {manifest_hash(out)}')
"

echo "E0 complete. Next: scripts/01_verify_schema.py --frozen-dir $OUTPUT_DIR  [GATE 0]"
