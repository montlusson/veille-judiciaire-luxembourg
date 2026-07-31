#!/usr/bin/env bash
# Refuse tout fichier trop long, quel que soit le chemin par lequel il est arrivé.
set -euo pipefail
MAX="${MAX_LINES:-500}"
fail=0
for f in "$@"; do
  [ -f "$f" ] || continue
  n=$(awk 'END{print NR+0}' "$f")
  if [ "$n" -gt "$MAX" ]; then
    echo "$f : $n lignes (plafond $MAX)"
    fail=1
  fi
done
exit $fail
