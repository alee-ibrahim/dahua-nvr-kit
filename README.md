# dahua-nvr-kit

Scripts + a Claude Code skill for administering a fleet of **Dahua NVRs** (and their attached
ONVIF / Samsung / Hanwha cameras) over the RPC2 API: rearrange and retitle channels, recover
lost camera passwords from an encrypted NVR config backup, diagnose live-view lag, and tune
camera encode profiles. Built from real field work and generalized -- no site data.

> **Use only on NVRs/cameras you own or are authorized to administer.** This kit is for
> operators maintaining their own CCTV estate. Do not use it against devices you do not control.

## Features

- **Read-only survey** of every channel across the fleet (bound camera IP, lens index,
  connection state, title).
- **Config-backup export + decrypt** to recover the per-camera credentials the NVR stores --
  Dahua `MWPZWJGS` **v1** (base64 + AES-ECB + gzip, via the vendored bashis tool) and a
  best-effort **v2** (AES-OFB) path.
- **Channel rearrange / resort / retitle** from a declarative target-map JSON, applied over
  RPC2 (`RemoteDevice` / `RemoteChannel` / `ChannelTitle`), backup-first.
- **Verification** with per-channel snapshots and labelled **contact sheets**.
- **Encode diagnosis** (MJPEG mains, oversized subs, silly main profiles, decode budget) and
  **fixes** via ONVIF `SetVideoEncoderConfiguration`, Samsung/Hanwha SUNAPI, or the Dahua
  Encode CGI -- backup-first, verify-after, auto-revert on unreachable.
- Documented **known limitation**: these NVRs don't expose ONVIF main-stream profile selection
  via API, so a firmware-locked-MJPEG camera's main must be switched in the NVR web UI
  (exact click path in `docs/METHOD.md`).
- **Footage / clip export** of exact MP4 evidence clips from the recordings via the recommended
  companion tool **[nvrclip](https://github.com/yashau/nvrclip)** (credit: yashau) — Dahua and
  Hikvision, clock-corrected, multi-part spans, timestamp-trimmed. Referenced, not bundled; see
  `docs/footage-export.md`.

## Why session-cookie auth

The RPC2 client logs in with the two-step MD5 challenge-response and then rides the
`DhWebClientSessionID` cookie for all calls (including the CGI snapshot/export endpoints),
because HTTP Digest auth fails on several Dahua firmware builds. Login is attempted **once** --
never in a loop -- so you don't lock out the admin account.

## Install

```
git clone https://github.com/alee-ibrahim/dahua-nvr-kit
cd dahua-nvr-kit
pip install -r requirements.txt
```

## Configure (the credential pattern)

Secrets never live in the repo. Provide them one of two ways:

- **Environment**: `NVR_USERNAME` (default `admin`), `NVR_PASSWORD`, optional
  `DAHUA_KIT_CONFIG` (path to the config JSON).
- **Config file**: copy `examples/config.example.json` to `config.json` (gitignored) and fill
  in the NVR password, the NVR name->IP map, and any known camera creds.

Recovered camera credentials are written to `cameras.creds.json` (gitignored) by
`recover_creds.py` and merged automatically. The `.gitignore` excludes configs, creds, config
backups, decrypted trees, snapshots and contact sheets.

## Usage

```
cd scripts

python survey.py                              # read-only fleet inventory
python diagnose_encode.py                     # per-channel encode + lag flags

# recover camera creds from an NVR backup
python export_backup.py --out ../backups
python decrypt_config.py --infile ../backups/nvr-01-configExport-ext0.backup --key nvr
python recover_creds.py ../decrypted/nvr-01/Config/Config1 --out ../cameras.creds.json

# rearrange channels
python rearrange.py --map ../my-target-map.json nvr-01 --dry-run
python rearrange.py --map ../my-target-map.json nvr-01

# verify
python verify.py nvr-01 --snapshots ../snaps
python contact_sheet.py nvr-01 --out ../sheets

# encode fixes (one camera at a time)
python fix_encode.py onvif --ip 198.51.100.20 --profile "H.264" \
    --encoding H264 --w 640 --h 480 --fps 15 --bitrate 512 --gov 30
python fix_encode.py dahua --ip 198.51.100.30 --stream sub --fps 15 --bitrate 512
```

See `SKILL.md` for the full workflow/playbook and `docs/METHOD.md` for the protocol, decrypt
format, config-table schema, and the ONVIF-profile limitation.

## Safety

Back up before changing anything; change one device at a time; verify (snapshot, not just
`Connected`) and be ready to revert; never loop on a failed login; never commit secrets. The
scripts follow these by default.

## Credits / related tools

`third_party/DahuaConfigBackupDecEnc.py` is the v1 config-backup decrypter by **bashis**
(with XVR contributions by iTuneDVR), vendored unmodified with its attribution header intact.
See `third_party/README.md` and `NOTICE`.

**[nvrclip](https://github.com/yashau/nvrclip)** by **yashau** is the recommended companion tool
for **exporting MP4 clips** from NVR recordings (Dahua + Hikvision). It is **referenced, not
bundled** — its upstream license is unstated, so check before redistributing. See
`docs/footage-export.md`.

## License

MIT (2026) -- see `LICENSE`. The MIT license covers this kit's own code; the vendored
third-party file is under its author's terms.
