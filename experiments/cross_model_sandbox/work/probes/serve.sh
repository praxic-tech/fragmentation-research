#!/usr/bin/env bash
# Start llama-server for a sandbox model with the settings fixed for this study.
# usage: work/probes/serve.sh <gguf path> <port> <log file> [extra args...]
# -np 1 so the single slot gets the full 65,536 context; -fit off so llama.cpp
# cannot silently shrink it; -dev Vulkan0 so nothing lands on the iGPU.
set -euo pipefail
M="$1"; P="$2"; L="$3"; shift 3
exec runtime/llama-b12110-vulkan/llama-server.exe -m "$M" -dev Vulkan0 -ngl 99 \
  -c 65536 -np 1 -fit off --jinja --host 127.0.0.1 --port "$P" --no-webui "$@" > "$L" 2>&1
