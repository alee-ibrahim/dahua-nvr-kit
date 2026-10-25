#!/usr/bin/env python3
"""rearrange.py -- apply a target channel map to a Dahua NVR.

Rearranges / resorts which camera appears on which NVR channel, in what order, with what
title -- by writing three config tables over RPC2:

  * RemoteDevice  -- a uuid-keyed table of camera connection entries (IP, creds, name).
    We send a PARTIAL table containing only the entries we touch.
  * RemoteChannel -- a full list; entry i binds channel i+1 to a RemoteDevice uuid (``Device``)
    and selects the lens/stream index (``Channel``).
  * ChannelTitle  -- a full list; entry i is the on-screen name of channel i+1.

The device uuid for a camera IP is reused from the NVR's existing RemoteDevice table, so the
camera must already be registered on that NVR (this tool reorders / retitles / re-binds
existing registrations; it is not a camera-add wizard). Camera passwords are filled from the
kit config (lib/config.py) because a live getConfig masks them.

Safety: the current RemoteDevice/RemoteChannel/ChannelTitle are saved to a backup file BEFORE
any change. Use --dry-run to preview. Apply one NVR at a time, then run verify.py.

Target-map JSON (see examples/target-map.example.json):
    {
      "nvr-01": {
        "1": {"ip": "198.51.100.20", "lens": 0, "title": "Main Entrance"},
        "2": {"ip": "198.51.100.21", "lens": 0, "title": "Lobby"}
      }
    }

Usage:
    python rearrange.py --map target-map.json nvr-01 --dry-run
    python rearrange.py --map target-map.json nvr-01
"""
import argparse
import copy
import json
import os
import sys
import time

from lib import config as C
from lib.dahua_rpc import DahuaRPC


def build_ip_catalog(rd, rc):
    """Map camera IP -> device uuid, from the existing RemoteDevice/RemoteChannel."""
    cat = {}
    if not isinstance(rd, dict):
        return cat
    for uuid, ent in rd.items():
        addr = ent.get("Address")
        if addr:
            cat.setdefault(addr, uuid)
    return cat


def apply_map(name, host, user, pw, plan, cam_creds, backup_dir, dry_run):
    plan = {int(k): v for k, v in plan.items()}
    with DahuaRPC(host, user, pw) as rpc:
        rd = rpc.get_table("RemoteDevice") or {}
        rc = rpc.get_table("RemoteChannel") or []
        ct = rpc.get_table("ChannelTitle") or []

        # backup first
        os.makedirs(backup_dir, exist_ok=True)
        bpath = os.path.join(backup_dir, f"{name}-{int(time.time())}.backup.json")
        json.dump({"RemoteDevice": rd, "RemoteChannel": rc, "ChannelTitle": ct},
                  open(bpath, "w"), indent=1)
        print(f"{name}: backed up current config -> {bpath}")

        cat = build_ip_catalog(rd, rc)
        new_rc = copy.deepcopy(rc)
        new_ct = copy.deepcopy(ct)
        rd_partial = {}

        for ch, p in sorted(plan.items()):
            i = ch - 1
            if i < 0 or i >= len(new_rc):
                print(f"  ch{ch}: out of range (NVR has {len(new_rc)} channels) -- SKIP")
                continue
            ip = p["ip"]
            uuid = p.get("uuid") or cat.get(ip)
            if not uuid:
                print(f"  ch{ch}: camera {ip} not registered on {name} -- SKIP "
                      f"(register it first, or give an explicit uuid)")
                continue
            ent = copy.deepcopy(rd.get(uuid, {}))
            ent["Address"] = ip
            ent["Enable"] = True
            cc = cam_creds.get(ip)
            if cc:
                ent["UserName"] = cc["username"]
                ent["Password"] = cc["password"]
            if isinstance(ent.get("VideoInputs"), list) and ent["VideoInputs"]:
                ent["VideoInputs"][0]["Name"] = p.get("title", ent["VideoInputs"][0].get("Name"))
            rd_partial[uuid] = ent

            new_rc[i]["Device"] = uuid
            new_rc[i]["Channel"] = p.get("lens", new_rc[i].get("Channel", 0))
            new_rc[i]["Enable"] = True
            if i < len(new_ct):
                new_ct[i]["Name"] = p.get("title", new_ct[i].get("Name"))
            print(f"  ch{ch}: -> {ip} lens {new_rc[i]['Channel']} title '{p.get('title')}'")

        if dry_run:
            print(f"{name}: DRY RUN -- no changes written "
                  f"({len(rd_partial)} RemoteDevice, {len(new_rc)} RemoteChannel, "
                  f"{len(new_ct)} ChannelTitle would be sent)")
            return

        r1 = rpc.set_config("RemoteDevice", rd_partial)
        print("  setConfig RemoteDevice :", r1.get("result"), r1.get("error"))
        r2 = rpc.set_config("RemoteChannel", new_rc)
        print("  setConfig RemoteChannel:", r2.get("result"), r2.get("error"))
        r3 = rpc.set_config("ChannelTitle", new_ct)
        print("  setConfig ChannelTitle :", r3.get("result"), r3.get("error"))
        print(f"{name}: applied. Run verify.py next.")


def main():
    ap = argparse.ArgumentParser(description="Apply a target channel map to a Dahua NVR")
    ap.add_argument("nvrs", nargs="+", help="NVR name(s) from the map / config")
    ap.add_argument("--map", required=True, help="target-map JSON path")
    ap.add_argument("--backup-dir", default="./rearrange-backup")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    cam_creds = C.camera_creds(cfg)
    full_map = json.load(open(args.map, encoding="utf-8"))

    for name in args.nvrs:
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r} (not in config)", file=sys.stderr)
            continue
        plan = full_map.get(name)
        if not plan:
            print(f"# no plan for {name!r} in map", file=sys.stderr)
            continue
        print(f"\n== {name} ({host}) ==")
        apply_map(name, host, user, pw, plan, cam_creds, args.backup_dir, args.dry_run)


if __name__ == "__main__":
    main()
