#!/usr/bin/env bash
# Load test with made-up prompts: start one server config, sample GPU memory for the
# whole run, send the named loadtest_requests.py tests in order, stop the server.
# usage: bash work/probes/run_loadtest.sh SERVER_CONFIG OUT_DIR TEST [TEST ...]
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONDONTWRITEBYTECODE=1
PY=.venv/Scripts/python.exe
CFG="$1"; D="$2"; shift 2
mkdir -p "$D"; rm -f "$D/stop"
PORT=$($PY -I -c "import sys; sys.path.insert(0,'work/probes'); import server_ctl as s; print(s.CONFIGS[sys.argv[1]]['port'])" "$CFG")
$PY -I work/probes/server_ctl.py show "$CFG" > "$D/server_argv.json"
SPID=$($PY -I work/probes/server_ctl.py start "$CFG" "$D/server.log")
echo "server pid $SPID" | tee "$D/run.txt"
powershell -NoProfile -ExecutionPolicy Bypass -File work/probes/memsample.ps1 \
  -ProcId "$SPID" -OutCsv "$D/mem.csv" -StopFile "$D/stop" -IntervalMs 1000 &
for i in $(seq 1 300); do curl -s "http://127.0.0.1:$PORT/health" | grep -q '"ok"' && break; sleep 1; done
echo "ready after ~${i}s" | tee -a "$D/run.txt"
sleep 5
for T in "$@"; do
  echo "== $T start $(date +%T)" | tee -a "$D/run.txt"
  $PY -I work/probes/loadtest_requests.py "$T" "$D" 2>&1 | tee -a "$D/run.txt"
  echo "== $T end $(date +%T)" | tee -a "$D/run.txt"
done
curl -s "http://127.0.0.1:$PORT/slots" > "$D/slots_after.json"
touch "$D/stop"; sleep 3
$PY -I work/probes/server_ctl.py stop "$SPID" 90 | tee -a "$D/run.txt"
if tasklist //FI "PID eq $SPID" | grep -q llama-server; then
  taskkill //PID "$SPID" //F | tee -a "$D/run.txt"
fi
echo done | tee -a "$D/run.txt"
