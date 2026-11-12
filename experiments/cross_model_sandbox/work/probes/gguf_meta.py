"""Print selected key/value metadata from a GGUF file header (pure Python, read-only).

usage: python -I work/probes/gguf_meta.py FILE.gguf [substring ...]
Prints every scalar key whose name contains any of the substrings (default:
context_length, rope, sliding_window, architecture, name). Arrays are skipped.
"""
import struct
import sys

SCALARS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?",
           10: "<Q", 11: "<q", 12: "<d"}
STRING, ARRAY = 8, 9


def read_str(f):
    (n,) = struct.unpack("<Q", f.read(8))
    return f.read(n).decode("utf-8", "replace")


def read_val(f, t):
    if t in SCALARS:
        fmt = SCALARS[t]
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]
    if t == STRING:
        return read_str(f)
    if t == ARRAY:
        (et,) = struct.unpack("<I", f.read(4))
        (n,) = struct.unpack("<Q", f.read(8))
        if et in SCALARS:
            f.seek(n * struct.calcsize(SCALARS[et]), 1)
        else:
            for _ in range(n):
                read_val(f, et)
        return f"<array of {n}>"
    raise ValueError(f"unknown GGUF type {t}")


def main():
    path, subs = sys.argv[1], sys.argv[2:] or ["context_length", "rope", "sliding_window",
                                               "architecture", "general.name"]
    with open(path, "rb") as f:
        assert f.read(4) == b"GGUF", "not a GGUF file"
        version, n_tensors, n_kv = struct.unpack("<IQQ", f.read(20))
        print(f"{path}: GGUF v{version}, {n_tensors} tensors, {n_kv} keys")
        for _ in range(n_kv):
            key = read_str(f)
            (t,) = struct.unpack("<I", f.read(4))
            val = read_val(f, t)
            if any(s in key for s in subs) and not str(val).startswith("<array"):
                print(f"  {key} = {val}")


if __name__ == "__main__":
    main()
