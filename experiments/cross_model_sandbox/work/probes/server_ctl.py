"""Start or stop llama-server without any shell quoting.

The server gets its own hidden console, so it can later be stopped with a real
Ctrl+C. A graceful stop makes llama.cpp print its memory breakdown table on exit
(taskkill /F does not).

usage:
  python -I work/probes/server_ctl.py start CONFIG_NAME LOG_FILE   -> prints the PID
  python -I work/probes/server_ctl.py stop PID [TIMEOUT_S]
  python -I work/probes/server_ctl.py show CONFIG_NAME              -> prints the argv

Server configurations are written out below as Python lists; nothing is parsed
from a command line.
"""
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
BIN = SANDBOX / "runtime" / "llama-b12110-vulkan" / "llama-server.exe"
MODELS = SANDBOX / "runtime" / "models"
TEMPLATES = SANDBOX / "work" / "templates"

# Flags shared by every study server (see work/prereg_drafts).
COMMON = ["-dev", "Vulkan0", "-ngl", "99", "-np", "1", "-fit", "off", "--jinja",
          "--host", "127.0.0.1", "--no-webui", "--reasoning-format", "auto",
          "--no-cache-prompt", "--cache-ram", "0"]

CONFIGS = {
    # gpt-oss-20b at the Option B context, load only, verbose
    "gptoss-b-verbose": {
        "model": MODELS / "gpt-oss-20b-MXFP4.gguf", "ctx": 98304, "port": 8091,
        "extra": ["--chat-template-file", str(TEMPLATES / "gpt-oss-20b.fixed-date.jinja"), "-v"]},
    # gpt-oss-20b at the Option B context, prereg flags, rendered prompts logged
    "gptoss-b": {
        "model": MODELS / "gpt-oss-20b-MXFP4.gguf", "ctx": 98304, "port": 8091,
        "extra": ["--chat-template-file", str(TEMPLATES / "gpt-oss-20b.fixed-date.jinja"),
                  "--log-prompts-dir", str(SANDBOX / "work" / "probes" / "out" / "gptoss_b" / "prompts")]},
    # Gemma 4 12B at the Option B context
    "gemma-b": {
        "model": MODELS / "gemma-4-12b-it-qat-q4_0.gguf", "ctx": 163840, "port": 8092,
        "extra": []},
}


def argv_for(name):
    c = CONFIGS[name]
    return [str(BIN), "-m", str(c["model"]), "-c", str(c["ctx"]), "--port", str(c["port"]),
            *COMMON, *c["extra"]]


def start(name, log):
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    f = open(log, "wb")
    p = subprocess.Popen(argv_for(name), stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si,
                         cwd=str(SANDBOX))
    print(p.pid)


def stop(pid, timeout):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    SYNCHRONIZE, PROCESS_QUERY = 0x00100000, 0x1000
    h = k.OpenProcess(SYNCHRONIZE | PROCESS_QUERY, False, pid)
    if not h:
        print(f"no process {pid}")
        return 0
    k.FreeConsole()
    if not k.AttachConsole(pid):
        print(f"AttachConsole failed ({ctypes.get_last_error()})")
        return 1
    k.SetConsoleCtrlHandler(None, True)      # this helper ignores the Ctrl+C itself
    k.GenerateConsoleCtrlEvent(0, 0)          # CTRL_C_EVENT to the server's console
    r = k.WaitForSingleObject(h, int(timeout * 1000))
    k.FreeConsole()
    if r == 0:
        print(f"stopped {pid} gracefully")
        return 0
    print(f"{pid} still running after {timeout}s")
    return 2


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "start":
        start(sys.argv[2], sys.argv[3])
    elif cmd == "stop":
        sys.exit(stop(int(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 60))
    elif cmd == "show":
        print(json.dumps(argv_for(sys.argv[2]), indent=1))
