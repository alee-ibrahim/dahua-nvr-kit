"""Credential + inventory loader for dahua-nvr-kit.

Secrets never live in the repo. They come from, in order of precedence:

1. Environment variables:
     NVR_USERNAME        (default "admin")
     NVR_PASSWORD        (the shared NVR admin password)
     DAHUA_KIT_CONFIG    (path to a config JSON; default ./config.json)
2. A gitignored JSON config file (see config.example.json), structured:
     {
       "nvr":      {"username": "admin", "password": "..."},
       "nvrs":     {"nvr-01": "192.0.2.10", "nvr-02": "192.0.2.11"},
       "cameras":  {"198.51.100.20": {"username": "admin", "password": "..."}}
     }
3. A gitignored recovered-camera-credentials file (default cameras.creds.json),
   produced by recover_creds.py, merged over "cameras".

No password is ever printed by these helpers.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def _config_path():
    return os.environ.get("DAHUA_KIT_CONFIG") or os.path.join(REPO, "config.json")


def load_config():
    """Return the merged config dict. Env vars override file values for the NVR
    credential; recovered camera creds (if present) are merged into cameras."""
    cfg = {"nvr": {"username": "admin", "password": ""}, "nvrs": {}, "cameras": {}}
    path = _config_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            disk = json.load(fh)
        for key in ("nvr", "nvrs", "cameras"):
            if key in disk:
                cfg[key] = disk[key]

    # env overrides for the NVR login
    cfg.setdefault("nvr", {})
    cfg["nvr"]["username"] = os.environ.get("NVR_USERNAME", cfg["nvr"].get("username", "admin"))
    if os.environ.get("NVR_PASSWORD"):
        cfg["nvr"]["password"] = os.environ["NVR_PASSWORD"]

    # merge recovered camera creds if present
    creds_path = os.environ.get("DAHUA_KIT_CAM_CREDS") or os.path.join(REPO, "cameras.creds.json")
    if os.path.exists(creds_path):
        with open(creds_path, encoding="utf-8") as fh:
            cfg["cameras"].update(json.load(fh))

    return cfg


def nvr_login(cfg=None):
    cfg = cfg or load_config()
    n = cfg.get("nvr", {})
    user = n.get("username") or "admin"
    pw = n.get("password") or ""
    if not pw:
        raise SystemExit(
            "No NVR password configured. Set NVR_PASSWORD or add it to config.json "
            "(see config.example.json)."
        )
    return user, pw


def nvrs(cfg=None):
    cfg = cfg or load_config()
    return dict(cfg.get("nvrs", {}))


def camera_creds(cfg=None):
    cfg = cfg or load_config()
    return dict(cfg.get("cameras", {}))
