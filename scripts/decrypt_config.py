#!/usr/bin/env python3
"""decrypt_config.py -- decrypt a Dahua config backup (configFileExport.backup).

Dahua config backups begin with the magic ``MWPZWJGS`` (or ``DHRDENFR`` for some
VTH exports). Two on-disk encodings are seen in the wild:

  * v1 (the common NVR/XVR form): after an 8-byte magic + 1 version byte, the body is
    base64 -> AES-ECB -> a small header (version, size, trailing MD5) wrapping a gzip
    (.tgz) of the config tree. The AES key is derived from a device-class string via
    Dahua's obfuscation (``nvr`` -> ``DahuaNVR``, ``xvr`` -> ``DahuaHCVR``, or the
    device HWID/model for cameras). This v1 path is implemented by bashis'
    DahuaConfigBackupDecEnc.py, bundled under ../third_party (credit preserved); this
    script shells out to it when ``--mode v1`` (default).

  * v2 (seen on some newer firmware): the same magic but the body is an AES stream
    cipher (OFB) rather than ECB-over-base64. ``--mode v2`` attempts a set of candidate
    keys/IVs and reports which produced a gzip stream. This is best-effort; v1 covers
    the devices this kit was built against.

Only run this on backups from devices you own or administer.

Usage:
    python decrypt_config.py --infile export.backup --key nvr            # v1
    python decrypt_config.py --infile export.backup --mode v2 --out out.tgz
"""
import argparse
import base64
import gzip
import os
import subprocess
import sys
from hashlib import md5
from struct import unpack

THIRD_PARTY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "third_party", "DahuaConfigBackupDecEnc.py")

DH_STRING = ("yaojinfucrang,yixitgchuanfei.vhuanglaiwaerqingfemgsheng,qiangeningerbaiyune."
             "tuiyuanlvzbu,qilingxengzezhizfn;yeshuilhuhua,guakgzhaolinqhuanzhibi."
             "zimeiju,ebnanbing.")


def _obf_key(clear):
    """Dahua obfuscation: XOR each char with its 1-based index, then md5-hex."""
    k = "".join(chr(ord(c) ^ (i + 1)) for i, c in enumerate(clear))
    return md5(k.encode("latin-1")).hexdigest()


def _backup_key(clear_text, idx):
    if clear_text == "nvr":
        return _obf_key("DahuaNVR")
    if clear_text == "xvr":
        return _obf_key("DahuaHCVR")
    key = clear_text.encode() + b"\x00" * 16
    key = md5(key).digest()
    key += DH_STRING[idx].encode()
    key = md5(key).digest()
    key = md5(key).hexdigest()[8:].encode()
    key += b"\x00" * (32 - (len(key) % 32))
    return key.decode()


def v1(infile, key):
    """Delegate to the bundled bashis tool (handles v1 ECB + MD5 verify + gzip)."""
    if not os.path.exists(THIRD_PARTY):
        sys.exit(f"bundled decrypter not found at {THIRD_PARTY}")
    cmd = [sys.executable, THIRD_PARTY, "--infile", infile, "--key", key]
    print("Running:", " ".join(cmd))
    raise SystemExit(subprocess.call(cmd))


def v2(infile, out, keys):
    """Best-effort AES-OFB decrypt attempt. Reports candidate keys/IVs that yield gzip."""
    from Crypto.Cipher import AES  # pycryptodome
    data = open(infile, "rb").read()
    if data[:8] not in (b"MWPZWJGS", b"DHRDENFR"):
        print("warning: unexpected magic", data[:8])
    hdr_iv = data[9:25]
    body = base64.b64decode(data[25:].rstrip(b"\x00")[: len(data[25:].rstrip(b"\x00")) // 4 * 4])

    candidates = {}
    for k in keys:
        candidates[k] = _obf_key(k)
    candidates["DahuaNVR"] = _obf_key("DahuaNVR")
    candidates["DahuaHCVR"] = _obf_key("DahuaHCVR")

    GZ = b"\x1f\x8b"
    found = None
    for name, kv in candidates.items():
        kb = kv.encode()
        kb = (kb + b"\x00" * 32)[:32]
        for mode, nm in [(AES.MODE_OFB, "OFB"), (AES.MODE_CFB, "CFB")]:
            try:
                o = AES.new(kb, mode, iv=hdr_iv).decrypt(body)
            except Exception:
                continue
            if GZ in o[:16]:
                start = o.find(GZ)
                print(f"*** candidate hit: key={name} mode={nm} gzip@{start}")
                found = o[start:]
    if found and out:
        try:
            payload = gzip.decompress(found)
        except Exception:
            payload = found
        open(out, "wb").write(payload)
        print("wrote", out, len(payload), "bytes")
    elif not found:
        print("no candidate produced a gzip stream. v2 format may differ on this firmware; "
              "capture the backup and extend the candidate list.")


def main():
    ap = argparse.ArgumentParser(description="Decrypt a Dahua config backup")
    ap.add_argument("--infile", required=True)
    ap.add_argument("--mode", choices=["v1", "v2"], default="v1")
    ap.add_argument("--key", default="nvr",
                    help="v1: device class (nvr/xvr) or HWID/model string")
    ap.add_argument("--out", help="v2: output file for the decrypted tree")
    ap.add_argument("--try-keys", nargs="*", default=["nvr", "xvr"],
                    help="v2: extra candidate device-class/model strings")
    args = ap.parse_args()
    if args.mode == "v1":
        v1(args.infile, args.key)
    else:
        v2(args.infile, args.out, args.try_keys)


if __name__ == "__main__":
    main()
