#!/usr/bin/env python3
"""verify.py -- read back NVR channel bindings + live connection state.

After a rearrange or any change, confirm each channel is bound to the expected camera and is
``Connected``. Optionally fetch a snapshot per channel (saved to a gitignored dir) to prove
real video, not just reachability.

Usage:
    python verify.py nvr-01
    python verify.py nvr-01 --snapshots ./snaps
    python verify.py --json nvr-01 nvr-02
"""
import argparse
import json
import os
import sys

from lib import config as C
from lib.dahua_rpc import DahuaRPC


def verify_one(name, host, user, pw, snap_dir=None):
    rows = []
    with DahuaRPC(host, user, pw) as rpc:
        rd = rpc.get_table("RemoteDevice") or {}
        rc = rpc.get_table("RemoteChannel") or []
        ct = rpc.get_table("ChannelTitle") or []
        st = rpc.camera_states()
        for i in range(len(rc)):
            dev = rc[i].get("Device")
            ent = rd.get(dev, {}) if isinstance(rd, dict) else {}
            row = {
                "ch": i + 1, "ip": ent.get("Address"), "lens": rc[i].get("Channel"),
                "state": st.get(i, "?"),
                "title": ct[i].get("Name") if i < len(ct) else None,
            }
            if snap_dir:
                os.makedirs(snap_dir, exist_ok=True)
                blob = rpc.snapshot(i + 1)
                if blob:
                    fn = os.path.join(snap_dir, f"{name}-ch{i + 1:02d}.jpg")
                    open(fn, "wb").write(blob)
                    row["snapshot"] = "ok"
                else:
                    row["snapshot"] = "no-image"
            rows.append(row)
    return {"nvr": name, "host": host, "channels": rows}


def main():
    ap = argparse.ArgumentParser(description="Verify NVR channel bindings + state")
    ap.add_argument("nvrs", nargs="+")
    ap.add_argument("--snapshots", metavar="DIR", help="also save a snapshot per channel")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    results = []
    for name in args.nvrs:
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r}", file=sys.stderr)
            continue
        try:
            results.append(verify_one(name, host, user, pw, args.snapshots))
        except Exception as e:
            results.append({"nvr": name, "host": host, "error": repr(e)[:160]})

    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        print(f"\n== {r['nvr']} ({r['host']}) ==")
        if r.get("error"):
            print("  ERROR:", r["error"])
            continue
        for c in r["channels"]:
            extra = f" snap={c['snapshot']}" if "snapshot" in c else ""
            print(f"  ch{c['ch']:02d}  {str(c['ip']):>16}  lens {c['lens']}  "
                  f"state={str(c['state']):<12} '{c['title']}'{extra}")


if __name__ == "__main__":
    main()
