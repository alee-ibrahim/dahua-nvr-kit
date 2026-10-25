#!/usr/bin/env python3
"""export_backup.py -- download the encrypted config backup from each NVR.

Logs in over RPC2 (session-cookie auth) and GETs /cgi-bin/configFileExport.backup.
The downloaded file is encrypted (magic MWPZWJGS); decrypt it with decrypt_config.py and
recover camera creds with recover_creds.py.

Output goes to a gitignored directory (default ./decrypted-input, you choose). Read-only on
the device (export does not change config).

Usage:
    python export_backup.py --out ./backups
    python export_backup.py nvr-01 --out ./backups
"""
import argparse
import os
import sys

from lib import config as C
from lib.dahua_rpc import DahuaRPC


def main():
    ap = argparse.ArgumentParser(description="Export encrypted config backups from NVRs")
    ap.add_argument("nvrs", nargs="*")
    ap.add_argument("--out", default="./backups")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    for name in (args.nvrs or list(fleet)):
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r}", file=sys.stderr)
            continue
        try:
            with DahuaRPC(host, user, pw) as rpc:
                got = False
                for ext in (0, 1):
                    blob = rpc.export_config_backup(ext)
                    if blob:
                        fn = os.path.join(args.out, f"{name}-configExport-ext{ext}.backup")
                        open(fn, "wb").write(blob)
                        print(f"{name} ({host}): wrote {fn} ({len(blob)} bytes) magic={blob[:8]}")
                        got = True
                if not got:
                    print(f"{name} ({host}): no backup returned")
        except Exception as e:
            print(f"{name} ({host}): ERROR {repr(e)[:160]}")


if __name__ == "__main__":
    main()
