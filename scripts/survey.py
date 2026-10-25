#!/usr/bin/env python3
"""survey.py -- read-only inventory of a Dahua NVR fleet.

For each configured NVR, logs in once and prints a per-channel table:
bound camera IP, lens/stream index, connection state, and channel title.
Nothing is written to the devices. Use this first, before any change.

Usage:
    python survey.py                 # all NVRs in config.json
    python survey.py nvr-01 nvr-02   # named NVRs only
    python survey.py --json          # machine-readable output
"""
import argparse
import json
import sys

from lib import config as C
from lib.dahua_rpc import DahuaRPC


def survey_one(name, host, user, pw):
    rows = []
    try:
        with DahuaRPC(host, user, pw) as rpc:
            rd = rpc.get_table("RemoteDevice") or {}
            rc = rpc.get_table("RemoteChannel") or []
            ct = rpc.get_table("ChannelTitle") or []
            st = rpc.camera_states()
            for i in range(len(rc)):
                dev = rc[i].get("Device")
                ent = rd.get(dev, {}) if isinstance(rd, dict) else {}
                rows.append({
                    "ch": i + 1,
                    "ip": ent.get("Address"),
                    "port": ent.get("Port"),
                    "lens": rc[i].get("Channel"),
                    "state": st.get(i, "?"),
                    "title": ct[i].get("Name") if i < len(ct) else None,
                })
    except Exception as e:
        return {"nvr": name, "host": host, "error": repr(e)[:160], "channels": []}
    return {"nvr": name, "host": host, "channels": rows}


def main():
    ap = argparse.ArgumentParser(description="Read-only Dahua NVR fleet survey")
    ap.add_argument("nvrs", nargs="*", help="NVR names from config (default: all)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    names = args.nvrs or list(fleet)
    results = []
    for name in names:
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r} (not in config)", file=sys.stderr)
            continue
        results.append(survey_one(name, host, user, pw))

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results:
        print(f"\n== {r['nvr']} ({r['host']}) ==")
        if r.get("error"):
            print("  ERROR:", r["error"])
            continue
        for c in r["channels"]:
            print(f"  ch{c['ch']:02d}  {str(c['ip']):>16}:{c['port']}  lens {c['lens']}  "
                  f"state={str(c['state']):<12} '{c['title']}'")


if __name__ == "__main__":
    main()
