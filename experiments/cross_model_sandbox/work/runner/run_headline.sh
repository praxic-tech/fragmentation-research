#!/usr/bin/env bash
# Study run: start the preregistered server, sample GPU memory, run the runner,
# then stop the sampler and the server whatever the runner's exit.
# usage: bash work/runner/run_headline.sh SERVER_CONFIG MODEL_SLUG [runner flags]
set -uo pipefail
cd "$(dirname "$0")/../.."
export PYTHONDONTWRITEBYTECODE=1
PY=.venv/Scripts/python.exe
CFG="$1"; SLUG="$2"; shift 2
D="logs/$SLUG"; mkdir -p "$D/prompts"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
rm -f "$D/stop"
PORT=$($PY -I -c "import sys; sys.path.insert(0,'work/probes'); import server_ctl as s; print(s.CONFIGS[sys.argv[1]]['port'])" "$CFG")
$PY -I work/probes/server_ctl.py show "$CFG" > "$D/server_argv.$STAMP.json"
SPID=$($PY -I work/probes/server_ctl.py start "$CFG" "$D/server.$STAMP.log")
echo "$(date -u +%FT%TZ) server pid $SPID ($CFG)" | tee -a "$D/launcher.log"
powershell -NoProfile -ExecutionPolicy Bypass -File work/probes/memsample.ps1 \
  -ProcId "$SPID" -OutCsv "$D/mem.$STAMP.csv" -StopFile "$D/stop" -IntervalMs 5000 &
for i in $(seq 1 300); do curl -s "http://127.0.0.1:$PORT/health" | grep -q '"ok"' && break; sleep 1; done
echo "$(date -u +%FT%TZ) server ready after ~${i}s" | tee -a "$D/launcher.log"
$PY -I work/runner/runner.py "$SLUG" "$@"
RC=$?
echo "$(date -u +%FT%TZ) runner exited $RC" | tee -a "$D/launcher.log"
curl -s "http://127.0.0.1:$PORT/slots" > "$D/slots_after.$STAMP.json"
touch "$D/stop"; sleep 6
taskkill //PID "$SPID" //F | tee -a "$D/launcher.log"
exit $RC
