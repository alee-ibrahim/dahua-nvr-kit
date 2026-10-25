"""Dahua camera encode helper via the configManager CGI (digest auth).

Credentials from the kit config (lib/config.py). No password is printed. Used to read and
tune a Dahua camera's Encode config directly (e.g. drop an absurd main fps, or trim an
oversized sub-stream).
"""
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


def get_encode(ip, timeout=15):
    r = requests.get(
        f"http://{ip}/cgi-bin/configManager.cgi?action=getConfig&name=Encode",
        auth=_auth(ip), timeout=timeout,
    )
    return r.status_code, r.text


def parse_stream(text, fmt, idx=0, ch=0):
    """fmt = MainFormat|ExtraFormat -> dict of Video.* for Encode[ch].fmt[idx]."""
    pref = f"table.Encode[{ch}].{fmt}[{idx}].Video."
    out = {}
    for line in text.splitlines():
        if line.startswith(pref):
            k, _, v = line[len(pref):].partition("=")
            out[k] = v
    return out


def set_encode(ip, params, ch=0, timeout=20):
    """params: list of (keypath, value) relative to Encode[ch],
    e.g. [('MainFormat[0].Video.FPS', '25')]. Returns (ok, status, body)."""
    q = "&".join(f"Encode[{ch}].{k}={quote(str(v))}" for k, v in params)
    r = requests.get(
        f"http://{ip}/cgi-bin/configManager.cgi?action=setConfig&{q}",
        auth=_auth(ip), timeout=timeout,
    )
    ok = r.status_code == 200 and "OK" in r.text
    return ok, r.status_code, r.text.strip()[:150]
