#!/usr/bin/env python3
"""fix_encode.py -- apply an encode fix to a single camera. Backup-first, verify-after.

Three backends:

  onvif   -- ONVIF SetVideoEncoderConfiguration. Select the encoder by its profile name and
             set codec/resolution/fps/bitrate/GOP. Backs up every VideoEncoderConfiguration
             to a JSON first; if the camera goes unreachable after the change, restores it.
  dahua   -- Dahua camera Encode CGI. Tune MAIN/SUB fps / bitrate directly.
  sunapi  -- Hanwha/Samsung SUNAPI videoprofile update. (Legacy models may firmware-lock the
             primary MJPEG profile and reject codec/fps changes -- the NG response is reported.)

Operate on ONE camera at a time, then re-run verify.py / contact_sheet.py against the NVR.
Credentials come from the kit config (lib/config.py). No password is printed.

Examples:
    # Trim a Samsung sub-stream to a light H.264 tile stream over ONVIF:
    python fix_encode.py onvif --ip 198.51.100.20 --profile "H.264" \\
        --encoding H264 --w 640 --h 480 --fps 15 --bitrate 512 --gov 30

    # Drop a Dahua 4K main from 50fps to 25fps:
    python fix_encode.py dahua --ip 198.51.100.30 --stream main --fps 25

    # Trim a Dahua oversized sub:
    python fix_encode.py dahua --ip 198.51.100.30 --stream sub --fps 15 --bitrate 512
"""
import argparse
import json
import os
import sys
import time

from lib import onvif as O
from lib import dahua_cam as D
from lib import sunapi as S

BK = "./encode-backup"


def _backup_dir():
    os.makedirs(BK, exist_ok=True)
    return BK


def fix_onvif(args):
    ip = args.ip
    sc, root, raw = O.get_profiles(ip)
    if root is None:
        sys.exit(f"{ip}: no ONVIF profiles (sc={sc})")
    profs = O.parse_profiles(root)
    byname = {p["profile_name"]: p for p in profs}
    if args.profile not in byname:
        sys.exit(f"{ip}: profile {args.profile!r} not found. Available: "
                 + ", ".join(p['profile_name'] for p in profs))
    # backup all VEC XML (once; keep true original)
    bpath = os.path.join(_backup_dir(), f"{ip}.json")
    if not os.path.exists(bpath):
        vecs = {}
        for p in profs:
            vt = p.get("vec_token")
            if vt and vt not in vecs:
                _, cfg, _ = O.get_vec(ip, vt)
                vecs[vt] = cfg
        json.dump({"ip": ip, "ts": time.time(), "profiles": profs, "vecs": vecs},
                  open(bpath, "w"), indent=1)
        print(f"{ip}: backed up profiles -> {bpath}")
    else:
        print(f"{ip}: backup exists ({bpath}), keeping original")

    vt = byname[args.profile]["vec_token"]
    _, cfg, _ = O.get_vec(ip, vt)
    if not cfg:
        sys.exit(f"{ip}: could not read VEC for {args.profile}")
    print(f"{ip}: before: {O.summarize_vec(cfg)}")
    new = O.transform_vec(cfg, args.encoding, args.w, args.h, args.fps, args.bitrate,
                          gov=args.gov, h264profile=args.h264profile, quality=args.quality)
    ok, fault, _ = O.set_vec(ip, new)
    print(f"{ip}: set_vec ok={ok} fault={fault}")

    time.sleep(0.5)
    sc2, info, _ = O.get_device_info(ip)
    if not info:
        print(f"{ip}: UNREACHABLE after change -- restoring from backup")
        bk = json.load(open(bpath))
        orig = bk["vecs"].get(vt)
        if orig:
            O.set_vec(ip, orig)
        sc3, info2, _ = O.get_device_info(ip)
        print(f"{ip}: restore {'ok' if info2 else 'FAILED'}")
        return
    _, cfg2, _ = O.get_vec(ip, vt)
    print(f"{ip}: after : {O.summarize_vec(cfg2)}")


def fix_dahua(args):
    ip = args.ip
    sc, text = D.get_encode(ip)
    if sc != 200:
        sys.exit(f"{ip}: getEncode HTTP {sc}")
    fmt = "MainFormat" if args.stream == "main" else "ExtraFormat"
    open(os.path.join(_backup_dir(), f"{ip}-dahua-encode.txt"), "w", encoding="utf-8").write(text)
    print(f"{ip}: backed up Encode -> encode-backup/{ip}-dahua-encode.txt")
    print(f"{ip}: before: {D.parse_stream(text, fmt)}")
    params = []
    if args.fps is not None:
        params.append((f"{fmt}[0].Video.FPS", args.fps))
    if args.bitrate is not None:
        params.append((f"{fmt}[0].Video.BitRate", args.bitrate))
    if args.gov is not None:
        params.append((f"{fmt}[0].Video.GOP", args.gov))
    if not params:
        sys.exit("nothing to change (give --fps / --bitrate / --gov)")
    ok, st, body = D.set_encode(ip, params)
    print(f"{ip}: set_encode ok={ok} http={st} body={body}")
    _, text2 = D.get_encode(ip)
    print(f"{ip}: after : {D.parse_stream(text2, fmt)}")


def fix_sunapi(args):
    ip = args.ip
    profiles, _ = S.view_profiles(ip)
    if args.profile_num not in profiles:
        sys.exit(f"{ip}: profile {args.profile_num} not found. Have: {sorted(profiles)}")
    cur = profiles[args.profile_num]
    overrides = {}
    if args.encoding:
        overrides["EncodingType"] = args.encoding
    if args.resolution:
        overrides["Resolution"] = args.resolution
    if args.fps is not None:
        overrides["FrameRate"] = str(args.fps)
    if args.bitrate is not None:
        overrides["Bitrate"] = str(args.bitrate)
    ok, st, body, path = S.update_profile(ip, args.profile_num, cur, overrides)
    print(f"{ip}: update ok={ok} http={st} body={body}")
    if not ok:
        print(f"{ip}: NOTE legacy models firmware-lock the primary profile and reject changes.")


def main():
    ap = argparse.ArgumentParser(description="Apply an encode fix to one camera (backup-first)")
    sub = ap.add_subparsers(dest="method", required=True)

    o = sub.add_parser("onvif")
    o.add_argument("--ip", required=True)
    o.add_argument("--profile", required=True, help="ONVIF profile name to modify")
    o.add_argument("--encoding", default="H264", choices=["H264", "JPEG"])
    o.add_argument("--w", type=int, required=True)
    o.add_argument("--h", type=int, required=True)
    o.add_argument("--fps", type=int, required=True)
    o.add_argument("--bitrate", type=int, required=True)
    o.add_argument("--gov", type=int, default=30)
    o.add_argument("--h264profile", default="High")
    o.add_argument("--quality", type=int, default=None)

    d = sub.add_parser("dahua")
    d.add_argument("--ip", required=True)
    d.add_argument("--stream", choices=["main", "sub"], required=True)
    d.add_argument("--fps", type=int, default=None)
    d.add_argument("--bitrate", type=int, default=None)
    d.add_argument("--gov", type=int, default=None)

    s = sub.add_parser("sunapi")
    s.add_argument("--ip", required=True)
    s.add_argument("--profile-num", type=int, required=True)
    s.add_argument("--encoding", default=None)
    s.add_argument("--resolution", default=None)
    s.add_argument("--fps", type=int, default=None)
    s.add_argument("--bitrate", type=int, default=None)

    args = ap.parse_args()
    {"onvif": fix_onvif, "dahua": fix_dahua, "sunapi": fix_sunapi}[args.method](args)


if __name__ == "__main__":
    main()
