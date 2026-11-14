#!/usr/bin/env bash
# Runs one line of the sweep in order; a halt (non-zero exit) stops this line only.
# usage: run_line.sh <line-name> <slug>...
cd "$(dirname "$0")/../.."
line=$1; shift
for m in "$@"; do
  mkdir -p "logs/$m"
  echo "$(date -u +%FT%TZ) START $m" >> "logs/line_$line.log"
  PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -I work/runner/api_runner.py "$m" > "logs/$m/console.txt" 2>&1
  rc=$?
  echo "$(date -u +%FT%TZ) END $m rc=$rc" >> "logs/line_$line.log"
  if [ $rc -ne 0 ]; then echo "$(date -u +%FT%TZ) LINE STOPPED at $m" >> "logs/line_$line.log"; exit $rc; fi
done
echo "$(date -u +%FT%TZ) LINE DONE" >> "logs/line_$line.log"
