"""Merge exact clocks recovered by eol_scan.py into gametime_index.json.

This is the repair path for snapshots that predate the existing clock index or
were missed by an older source glob. Both values come from that snapshot's own
GameTimeSaveData; nothing is interpolated here.
"""
import json
import os
import sys


def main():
    work = os.environ.get("PALTL_WORK")
    if not work or len(sys.argv) != 2:
        raise SystemExit("PALTL_WORK=<dir> merge_gametime_scan.py <eol-scan.json>")
    path = os.path.join(work, "gametime_index.json")
    data = json.load(open(path))
    added = 0
    for row in json.load(open(sys.argv[1])):
        if not row.get("ok") or row.get("real_clock") is None or row.get("game_clock") is None:
            continue
        key = str(row["ts"])
        value = [row["real_clock"], row["game_clock"]]
        if data.get(key) != value:
            data[key] = value
            added += 1
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({k: data[k] for k in sorted(data, key=int)}, f)
    os.replace(tmp, path)
    print(f"gametime_index.json: merged {added} exact snapshot clocks; total={len(data)}")


if __name__ == "__main__":
    main()
