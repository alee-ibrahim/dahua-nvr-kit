"""Hanwha/Samsung SUNAPI (stw-cgi) helper for video-profile tuning.

Digest auth, credentials from the kit config (lib/config.py). No password is printed.
Useful on Samsung/Hanwha cameras whose video profiles are easier to read/write over SUNAPI
than ONVIF. Note: some legacy models firmware-lock the primary (MJPEG) profile and reject
any codec/fps change on it -- handle the NG/604 response gracefully.
"""
import json
import os
from urllib.parse import quote

import requests
from requests.auth import HTTPDigestAuth

from . import config as _cfg

_CREDS = None


def _creds():
    global _CREDS
    if _CREDS is None:
        _CREDS = _cfg.camera_creds()
    return _CREDS


def _auth(ip):
    c = _creds()[ip]
    return HTTPDigestAuth(c["username"], c["password"])


def get(ip, path, timeout=15):
    return requests.get(f"http://{ip}{path}", auth=_auth(ip), timeout=timeout)


def view_profiles(ip):
    """Return ({profile_num: {field: value}}, raw_text) from videoprofile view."""
    import re
    t = get(ip, "/stw-cgi/media.cgi?msubmenu=videoprofile&action=view").text
    out = {}
    for line in t.replace("\r", "").split("\n"):
        m = re.match(r"Channel\.0\.Profile\.(\d+)\.(.+?)=(.*)$", line.strip())
        if m:
            out.setdefault(int(m.group(1)), {})[m.group(2)] = m.group(3)
    return out, t


UPDATE_FIELDS = [
    "Name", "ATCTrigger", "ATCMode", "ATCSensitivity", "ATCLimit",
    "SVNPMulticastEnable", "SVNPMulticastAddress", "SVNPMulticastPort", "SVNPMulticastTTL",
    "RTPMulticastEnable", "RTPMulticastAddress", "RTPMulticastPort", "RTPMulticastTTL",
    "EncodingType", "Resolution", "CropEncodingEnable", "CropAreaCoordinate",
    "FrameRate", "CompressionLevel", "Bitrate",
    "H264.BitrateControlType", "H264.GOVLength", "H264.PriorityType", "H264.Profile",
    "H264.EntropyCoding", "H264.SmartCodecEnable", "AudioInputEnable",
]

H264_DEFAULTS = {
    "H264.BitrateControlType": "VBR", "H264.GOVLength": "30", "H264.PriorityType": "FrameRate",
    "H264.Profile": "High", "H264.EntropyCoding": "CAVLC", "H264.SmartCodecEnable": "False",
}


def build_update(pnum, cur, overrides):
    """cur = current field dict; overrides applied on top. Returns update query path."""
    vals = dict(cur)
    enc = overrides.get("EncodingType", vals.get("EncodingType"))
    if enc == "H264":
        for k, v in H264_DEFAULTS.items():
            vals.setdefault(k, v)
    vals.update(overrides)
    # multicast ports must satisfy schema min 1024 even when disabled
    for pk in ("SVNPMulticastPort", "RTPMulticastPort"):
        try:
            if int(vals.get(pk, "0")) < 1024:
                vals[pk] = "1024"
        except ValueError:
            vals[pk] = "1024"
    q = ["Channel=0", f"Profile={pnum}"]
    for f in UPDATE_FIELDS:
        if f.startswith("H264.") and enc != "H264":
            continue
        q.append(f"{f}={quote(str(vals.get(f, '')), safe=',')}")
    return "/stw-cgi/media.cgi?msubmenu=videoprofile&action=update&" + "&".join(q)


def update_profile(ip, pnum, cur, overrides):
    path = build_update(pnum, cur, overrides)
    r = get(ip, path)
    body = r.text.strip()
    ok = r.status_code == 200 and not body.upper().startswith("NG") and "Error" not in body[:40]
    return ok, r.status_code, body[:200], path
