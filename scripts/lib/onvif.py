"""Minimal ONVIF client over raw SOAP + WS-Security UsernameToken (PasswordDigest).

No external SOAP stack required -- just ``requests`` and the stdlib XML parser. This is
enough to enumerate media profiles and get/set VideoEncoderConfiguration, which is all the
encode-tuning workflow needs. No password is ever printed.

Camera credentials are looked up from the kit config (see lib/config.py). You can also pass
user/pw explicitly.
"""
import base64
import datetime
import hashlib
import os
import re
import xml.etree.ElementTree as ET

import requests

from . import config as _cfg

TT = "{http://www.onvif.org/ver10/schema}"
TRT = "{http://www.onvif.org/ver10/media/wsdl}"
TDS = "{http://www.onvif.org/ver10/device/wsdl}"

_CREDS = None


def _creds():
    global _CREDS
    if _CREDS is None:
        _CREDS = _cfg.camera_creds()
    return _CREDS


def dev_xaddr(ip, port=80):
    return f"http://{ip}:{port}/onvif/device_service"


def media_xaddr(ip, port=80):
    return f"http://{ip}:{port}/onvif/media_service"


def _sec_header(user, pw):
    nonce = os.urandom(16)
    created = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + pw.encode()).digest()).decode()
    nonce_b64 = base64.b64encode(nonce).decode()
    return (
        '<s:Header><Security s:mustUnderstand="1" '
        'xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        f"<UsernameToken><Username>{user}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</Password>"
        '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{nonce_b64}</Nonce>"
        '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{created}</Created></UsernameToken></Security></s:Header>"
    )


def call(ip, xaddr, body, user=None, pw=None, timeout=15):
    """Send a SOAP operation. ``body`` is the inner XML of s:Body.
    Returns (status_code, ElementTree root or None, raw_text)."""
    c = _creds().get(ip, {})
    user = user or c.get("username", "admin")
    pw = pw if pw is not None else c.get("password", "")
    env = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        + _sec_header(user, pw) + "<s:Body>" + body + "</s:Body></s:Envelope>"
    )
    try:
        r = requests.post(
            xaddr, data=env.encode("utf-8"),
            headers={"Content-Type": "application/soap+xml; charset=utf-8"}, timeout=timeout,
        )
    except Exception as e:
        return (None, None, "EXC:" + repr(e)[:120])
    root = None
    try:
        root = ET.fromstring(r.content)
    except Exception:
        pass
    return (r.status_code, root, r.text)


def get_device_info(ip, port=80, user=None, pw=None):
    body = '<tds:GetDeviceInformation xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>'
    sc, root, raw = call(ip, dev_xaddr(ip, port), body, user, pw)
    info = {}
    if root is not None:
        for tag in ("Manufacturer", "Model", "FirmwareVersion", "SerialNumber"):
            el = root.find(".//" + TDS + tag)
            if el is not None:
                info[tag] = el.text
    return sc, info, raw


def get_profiles(ip, port=80, user=None, pw=None):
    body = '<trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl"/>'
    return call(ip, media_xaddr(ip, port), body, user, pw)


def parse_profiles(root):
    out = []
    if root is None:
        return out
    for pr in root.iter(TRT + "Profiles"):
        vec = pr.find(TT + "VideoEncoderConfiguration")
        d = {"profile_token": pr.get("token"), "profile_name": pr.findtext(TT + "Name")}
        if vec is not None:
            d["vec_token"] = vec.get("token")
            d["vec_name"] = vec.findtext(TT + "Name")
            d["encoding"] = vec.findtext(TT + "Encoding")
        out.append(d)
    return out


def get_vec(ip, token, port=80, user=None, pw=None):
    """Return (status, Configuration XML fragment or None, raw)."""
    body = (
        '<trt:GetVideoEncoderConfiguration xmlns:trt="http://www.onvif.org/ver10/media/wsdl">'
        f"<trt:ConfigurationToken>{token}</trt:ConfigurationToken>"
        "</trt:GetVideoEncoderConfiguration>"
    )
    sc, root, raw = call(ip, media_xaddr(ip, port), body, user, pw)
    m = re.search(r"<[^>]*:Configuration\b.*?</[^>]*:Configuration>", raw, re.S)
    return sc, (m.group(0) if m else None), raw


def summarize_vec(cfg_xml):
    if not cfg_xml:
        return None

    def g(tag):
        m = re.search(rf"<tt:{tag}>([^<]*)</tt:{tag}>", cfg_xml)
        return m.group(1) if m else None

    w = re.search(r"<tt:Width>([^<]*)</tt:Width>", cfg_xml)
    h = re.search(r"<tt:Height>([^<]*)</tt:Height>", cfg_xml)
    return {
        "name": g("Name"), "encoding": g("Encoding"),
        "w": w.group(1) if w else None, "h": h.group(1) if h else None,
        "fps": g("FrameRateLimit"), "bitrate": g("BitrateLimit"),
        "gov": g("GovLength"), "quality": g("Quality"),
    }


def transform_vec(cfg_xml, encoding, w, h, fps, bitrate, gov=30, h264profile="High", quality=None):
    """Return a modified Configuration XML with new encode parameters."""
    x = cfg_xml
    x = re.sub(r"<tt:Encoding>[^<]*</tt:Encoding>", f"<tt:Encoding>{encoding}</tt:Encoding>", x)
    x = re.sub(r"<tt:Width>[^<]*</tt:Width>", f"<tt:Width>{w}</tt:Width>", x)
    x = re.sub(r"<tt:Height>[^<]*</tt:Height>", f"<tt:Height>{h}</tt:Height>", x)
    x = re.sub(r"<tt:FrameRateLimit>[^<]*</tt:FrameRateLimit>",
               f"<tt:FrameRateLimit>{fps}</tt:FrameRateLimit>", x)
    x = re.sub(r"<tt:BitrateLimit>[^<]*</tt:BitrateLimit>",
               f"<tt:BitrateLimit>{bitrate}</tt:BitrateLimit>", x)
    if quality is not None:
        x = re.sub(r"<tt:Quality>[^<]*</tt:Quality>", f"<tt:Quality>{quality}</tt:Quality>", x)
    if encoding == "H264":
        h264 = (f"<tt:H264><tt:GovLength>{gov}</tt:GovLength>"
                f"<tt:H264Profile>{h264profile}</tt:H264Profile></tt:H264>")
        if re.search(r"<tt:H264>.*?</tt:H264>", x, re.S):
            x = re.sub(r"<tt:H264>.*?</tt:H264>", h264, x, flags=re.S)
        else:
            x = x.replace("</tt:RateControl>", "</tt:RateControl>" + h264, 1)
    else:  # JPEG: strip H264 block if present
        x = re.sub(r"<tt:H264>.*?</tt:H264>", "", x, flags=re.S)
    return x


def set_vec(ip, cfg_xml, port=80, user=None, pw=None):
    """SetVideoEncoderConfiguration with ForcePersistence. Returns (ok, fault, raw)."""
    body = (
        '<trt:SetVideoEncoderConfiguration xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        + cfg_xml
        + "<trt:ForcePersistence>true</trt:ForcePersistence></trt:SetVideoEncoderConfiguration>"
    )
    sc, root, raw = call(ip, media_xaddr(ip, port), body, user, pw)
    ok = sc == 200 and "SetVideoEncoderConfigurationResponse" in raw
    fault = None
    if not ok:
        fm = (re.search(r"<[^>]*:Text[^>]*>([^<]*)</[^>]*:Text>", raw)
              or re.search(r"<[^>]*:Reason>.*?([A-Za-z][^<]{3,})", raw, re.S))
        fault = (fm.group(1) if fm else raw[:200]).strip()
    return ok, fault, raw


def get_stream_uri(ip, profile_token, port=80, user=None, pw=None):
    body = (
        '<trt:GetStreamUri xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
        f"<trt:ProfileToken>{profile_token}</trt:ProfileToken></trt:GetStreamUri>"
    )
    sc, root, raw = call(ip, media_xaddr(ip, port), body, user, pw)
    m = re.search(r"<tt:Uri>([^<]*)</tt:Uri>", raw)
    return m.group(1) if m else None
