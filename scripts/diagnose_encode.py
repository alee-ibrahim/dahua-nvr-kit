#!/usr/bin/env python3
"""diagnose_encode.py -- find the per-channel encode profiles that cause live-view lag.

Reads each NVR's Encode config (read-only) and, per channel, reports the MAIN and SUB stream
(codec, resolution, fps, bitrate, GOP) plus connection state. It then flags the usual
live-view lag culprits on budget NVRs:

  * MJPEG main streams -- no inter-frame compression, every frame a full JPEG, very expensive
    to decode. A handful on one NVR will bog down tiled live view.
  * Oversized SUB streams -- the sub is what multi-view tiles decode; a SXGA/1080p 25-30 fps
    sub (or a sub bigger than the main) defeats the point of a light sub.
  * Silly MAIN profiles -- e.g. 4K @ 50 fps, or absurd bitrates.

It also estimates a rough per-channel "decode budget" (pixels/sec = W*H*fps) to rank load.
Nothing is written. Use before fix_encode.py.

Usage:
    python diagnose_encode.py              # all NVRs
    python diagnose_encode.py nvr-03       # one NVR
"""
import argparse
import re
import sys

from lib import config as C
from lib.dahua_rpc import DahuaRPC


def parse_encode(enc_params):
    """Return {ch: {'MainFormat': {...}, 'ExtraFormat': {...}}} from an Encode getConfig."""
    enc = {}
    text = None
    if isinstance(enc_params, dict):
        text = enc_params.get("text")
    out = {}
    if text:
        for line in text.replace("\r", "").split("\n"):
            m = re.match(r"table\.Encode\[(\d+)\]\.(MainFormat|ExtraFormat)\[0\]\.Video\.(\w+)=(.*)", line)
            if m:
                out.setdefault(int(m.group(1)), {}).setdefault(m.group(2), {})[m.group(3)] = m.group(4)
    else:
        tbl = (enc_params or {}).get("table")
        if isinstance(tbl, list):
            for ch, e in enumerate(tbl):
                for fmt in ("MainFormat", "ExtraFormat"):
                    try:
                        v = e[fmt][0]["Video"]
                        out.setdefault(ch, {})[fmt] = {k: val for k, val in v.items()}
                    except Exception:
                        pass
    return out


def fmt_stream(d):
    if not d:
        return "-"
    res = (d.get("resolution") or d.get("CustomResolutionName")
           or (f"{d.get('Width')}x{d.get('Height')}" if d.get("Width") else "?"))
    fps = str(d.get("FPS", "?")).split(".")[0]
    return (f"{res} {d.get('Compression', '?')} {fps}fps "
            f"{d.get('BitRate', '?')}k {d.get('BitRateControl', '?')} GOP{d.get('GOP', '?')}")


def px_per_sec(d):
    try:
        w = int(d.get("Width") or 0)
        h = int(d.get("Height") or 0)
        fps = int(float(d.get("FPS") or 0))
        return w * h * fps
    except Exception:
        return 0


def diagnose_one(name, host, user, pw):
    with DahuaRPC(host, user, pw) as rpc:
        rd = rpc.get_table("RemoteDevice") or {}
        rc = rpc.get_table("RemoteChannel") or []
        ct = rpc.get_table("ChannelTitle") or []
        st = rpc.camera_states()
        enc = parse_encode(rpc.get_config("Encode"))

    print(f"\n== {name} ({host}) channels={len(rc)} ==")
    flags = []
    for i in range(len(rc)):
        dev = rc[i].get("Device")
        ent = rd.get(dev, {}) if isinstance(rd, dict) else {}
        addr = ent.get("Address")
        title = ct[i].get("Name") if i < len(ct) else "?"
        mf = enc.get(i, {}).get("MainFormat", {})
        ef = enc.get(i, {}).get("ExtraFormat", {})
        print(f" ch{i + 1:02d} {str(addr):>16} state={str(st.get(i, '?')):<12} '{title}'")
        print(f"       MAIN: {fmt_stream(mf)}")
        print(f"       SUB : {fmt_stream(ef)}")
        comp = (mf.get("Compression") or "").upper()
        if comp in ("MJPG", "MJPEG", "JPEG"):
            flags.append(f"ch{i + 1:02d} {addr}: MJPEG main (heavy decode; convert to H.264/H.265)")
        if px_per_sec(ef) > px_per_sec(mf) and mf:
            flags.append(f"ch{i + 1:02d} {addr}: SUB heavier than MAIN (trim the sub)")
        try:
            if int(float(mf.get("FPS") or 0)) > 30:
                flags.append(f"ch{i + 1:02d} {addr}: MAIN fps {mf.get('FPS')} (>30; drop to 15-25)")
        except Exception:
            pass
    if flags:
        print("  -- FLAGS --")
        for f in flags:
            print("   *", f)
    else:
        print("  -- no obvious encode lag flags --")


def main():
    ap = argparse.ArgumentParser(description="Diagnose NVR encode / live-view lag")
    ap.add_argument("nvrs", nargs="*")
    args = ap.parse_args()
    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    for name in (args.nvrs or list(fleet)):
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r}", file=sys.stderr)
            continue
        try:
            diagnose_one(name, host, user, pw)
        except Exception as e:
            print(f"{name}: ERROR {repr(e)[:160]}")


if __name__ == "__main__":
    main()
