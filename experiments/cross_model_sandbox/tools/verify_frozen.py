"""Check that nothing under frozen/ has changed since the sandbox was created.

    python tools/verify_frozen.py          (from experiments/cross_model_sandbox/)

Exit status 0: every file listed in frozen/SHA256SUMS is present and
byte-identical, and frozen/ holds no file that is not listed (apart from Python
bytecode caches). Run it before and after every work session.
"""
import hashlib
import os
import sys

SB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = os.path.join(SB, "frozen")


def main():
    listed, bad = {}, []
    with open(os.path.join(FROZEN, "SHA256SUMS"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                h, rel = line.rstrip("\n").split("  ", 1)
                listed[rel] = h
    for rel, h in listed.items():
        p = os.path.join(FROZEN, rel)
        if not os.path.isfile(p):
            bad.append(f"MISSING  {rel}")
        elif hashlib.sha256(open(p, "rb").read()).hexdigest() != h:
            bad.append(f"CHANGED  {rel}")
    for dirpath, dirnames, files in os.walk(FROZEN):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in files:
            rel = os.path.relpath(os.path.join(dirpath, f), FROZEN).replace("\\", "/")
            if rel != "SHA256SUMS" and rel not in listed:
                bad.append(f"EXTRA    {rel}")
    if bad:
        print("frozen/ HAS BEEN ALTERED:")
        print("\n".join(bad))
        sys.exit(1)
    print(f"frozen/ intact: {len(listed)} files byte-identical to the snapshot")


if __name__ == "__main__":
    main()
