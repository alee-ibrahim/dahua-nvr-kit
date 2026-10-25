#!/usr/bin/env python3
"""contact_sheet.py -- build a labelled contact sheet of one NVR's channels.

Snapshots every channel and tiles them into a single JPEG with a caption bar per tile
(channel, camera IP, lens index, connection state, title). A fast visual check that the
rearrange landed and every tile shows the right camera.

Requires Pillow. Output JPEG is gitignored by default.

Usage:
    python contact_sheet.py nvr-01 --out ./sheets
"""
import argparse
import io
import os
import sys

from lib import config as C
from lib.dahua_rpc import DahuaRPC

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Pillow is required: pip install pillow")


def build_sheet(name, host, user, pw, out_dir, cols=4, cw=480, ch=300, pad=26):
    with DahuaRPC(host, user, pw) as rpc:
        rd = rpc.get_table("RemoteDevice") or {}
        rc = rpc.get_table("RemoteChannel") or []
        ct = rpc.get_table("ChannelTitle") or []
        st = rpc.camera_states()
        n = len(rc)
        snaps = {}
        for i in range(n):
            blob = rpc.snapshot(i + 1)
            if blob:
                snaps[i] = blob

    rows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * (ch + pad)), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for i in range(n):
        c = i % cols
        r = i // cols
        x, y = c * cw, r * (ch + pad)
        if i in snaps:
            im = Image.open(io.BytesIO(snaps[i])).convert("RGB").resize((cw, ch))
            sheet.paste(im, (x, y + pad))
        dev = rc[i].get("Device")
        ent = rd.get(dev, {}) if isinstance(rd, dict) else {}
        addr = ent.get("Address", "?")
        lens = rc[i].get("Channel")
        title = ct[i].get("Name") if i < len(ct) else "?"
        online = st.get(i, "?")
        label = f"ch{i + 1:02d} {addr} L{lens} [{online}] {title}"
        col = (90, 200, 90) if online == "Connected" else (200, 120, 120)
        dr.rectangle([x, y, x + cw, y + pad], fill=(0, 0, 0))
        dr.text((x + 4, y + 4), label, fill=col, font=font)

    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, f"{name}-sheet.jpg")
    sheet.save(fn, quality=85)
    print(f"{name}: saved {fn} ({sheet.size[0]}x{sheet.size[1]}, {len(snaps)}/{n} tiles)")


def main():
    ap = argparse.ArgumentParser(description="Build a labelled NVR contact sheet")
    ap.add_argument("nvrs", nargs="+")
    ap.add_argument("--out", default="./sheets")
    ap.add_argument("--cols", type=int, default=4)
    args = ap.parse_args()

    cfg = C.load_config()
    user, pw = C.nvr_login(cfg)
    fleet = C.nvrs(cfg)
    for name in args.nvrs:
        host = fleet.get(name)
        if not host:
            print(f"# unknown NVR {name!r}", file=sys.stderr)
            continue
        try:
            build_sheet(name, host, user, pw, args.out, cols=args.cols)
        except Exception as e:
            print(f"{name}: ERROR {repr(e)[:160]}")


if __name__ == "__main__":
    main()
