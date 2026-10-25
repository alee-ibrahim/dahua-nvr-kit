#!/usr/bin/env python3
"""recover_creds.py -- recover per-camera credentials from a decrypted NVR config.

An NVR stores the username/password it uses to pull each attached camera. When those camera
passwords have been lost but the NVR still has them, you can export + decrypt the NVR config
backup (see export_backup / decrypt_config.py) and read them back out.

This reads the decrypted config tree. In the v1 (.tgz) form the relevant file is usually
``Config/Config1`` -- a JSON document containing a ``NetCamera`` array, each entry having
``DeviceIP``, ``UserName``, ``Password`` and ``bEnable``.

Output is written to a GITIGNORED file (default cameras.creds.json at the repo root), in the
shape lib/config.py expects. Secrets are never printed; only a summary (count of cameras,
count of distinct passwords by hash) is shown.

Usage:
    python recover_creds.py Config1-nvr01.json Config1-nvr02.json
    python recover_creds.py --out cameras.creds.json decrypted/*/Config/Config1
"""
import argparse
import hashlib
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def h8(s):
    return hashlib.sha256(s.encode()).hexdigest()[:8]


def harvest(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        d = json.load(fh)
    creds = {}
    for e in (d.get("NetCamera") or []):
        ip = e.get("DeviceIP")
        pw = e.get("Password") or ""
        user = e.get("UserName") or "admin"
        if not ip or ip in ("0.0.0.0", "192.168.0.0") or not e.get("bEnable"):
            continue
        if not pw:
            continue
        creds[ip] = {"username": user, "password": pw}
    return creds


def main():
    ap = argparse.ArgumentParser(description="Recover camera creds from decrypted NVR config")
    ap.add_argument("files", nargs="+", help="decrypted Config1 JSON file(s)")
    ap.add_argument("--out", default=os.path.join(REPO, "cameras.creds.json"))
    args = ap.parse_args()

    all_creds = {}
    for f in args.files:
        if not os.path.exists(f):
            print(f"# missing: {f}")
            continue
        got = harvest(f)
        all_creds.update(got)
        print(f"{os.path.basename(f)}: {len(got)} camera(s)")

    pw_groups = {}
    for ip, c in all_creds.items():
        pw_groups.setdefault(h8(c["password"]), set()).add(ip)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(all_creds, fh, indent=1, ensure_ascii=False)

    print(f"\nwrote {args.out} with {len(all_creds)} camera(s)")
    print(f"distinct passwords (by hash, values not shown): {len(pw_groups)}")
    for h, ips in pw_groups.items():
        print(f"  {h}  used by {len(ips)} camera(s)")
    print("\nNOTE: this file is gitignored. Keep it out of the repo.")


if __name__ == "__main__":
    main()
