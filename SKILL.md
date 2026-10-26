---
name: dahua-nvr-kit
description: >-
  Administer a fleet of Dahua NVRs (and attached ONVIF/Samsung/Hanwha cameras) over the RPC2
  API. Use when asked to rearrange / resort / re-order NVR channels or retitle them; export an
  NVR config backup and decrypt it to recover lost camera passwords (Dahua MWPZWJGS v1 AES-ECB
  and the v2 AES-OFB variant); diagnose live-view lag (MJPEG main streams, oversized sub
  streams, silly main profiles, decode budget); tune camera encode via ONVIF
  SetVideoEncoderConfiguration, Samsung/Hanwha SUNAPI, or the Dahua Encode CGI; verify channels
  online with labelled contact sheets; or to understand why a firmware-locked-MJPEG camera's
  ONVIF main-stream profile cannot be changed (not via the API and not via the NVR web UI on
  these firmwares). Also for exporting footage / MP4 evidence clips from NVR recordings, which is
  done with the companion tool nvrclip (Dahua + Hikvision) — see docs/footage-export.md. For
  NVRs/cameras you own or administer.
---

# dahua-nvr-kit

A playbook + scripts for managing Dahua NVR fleets safely over the RPC2 API. Only use against
devices you own or are authorized to administer.

## Setup

1. `pip install -r requirements.txt`
2. Copy `examples/config.example.json` to `config.json` (gitignored) and fill in the NVR admin
   password, the NVR name->IP map, and any known camera creds. Or set `NVR_PASSWORD` in the
   environment. Recovered camera creds land in `cameras.creds.json` (gitignored).
3. All scripts live in `scripts/`; run them from there (`cd scripts && python survey.py`).

## Safety practices (always)

- **Back up before any change.** `rearrange.py` and `fix_encode.py` save the current config
  first; keep those backups.
- **One device at a time.** Apply, verify, then move on. Don't fan a change across the fleet
  before one device is confirmed healthy.
- **Verify, and be ready to revert.** `Connected` only means reachable -- pull a snapshot to
  confirm real video. If a change breaks video, restore from the backup.
- **No login-retry loops.** Dahua locks the admin account after a few bad passwords. Every
  helper logs in exactly once.
- **Never commit secrets.** Passwords come from env vars or the gitignored config/creds files.
  The `.gitignore` already excludes configs, creds, backups, decrypted trees and snapshots.

## Workflow

### 1. Read-only discovery / survey

```
python survey.py                 # per-channel: bound IP, lens, state, title (all NVRs)
python diagnose_encode.py        # per-channel main/sub codec/res/fps/bitrate + lag flags
```

Start here. Nothing is written. Build your mental model of the current layout and load.

### 2. Export config backup + decrypt -> recover camera credentials

When camera passwords are lost but the NVR still holds them:

```
python export_backup.py --out ./backups                 # GET configFileExport.backup
python decrypt_config.py --infile ./backups/nvr-01-configExport-ext0.backup --key nvr
# (v1: base64 + AES-ECB wrapping a gzip; vendored bashis tool. v2: --mode v2 for the OFB form)
# extract the resulting .tgz, then:
python recover_creds.py decrypted/nvr-01/Config/Config1 --out ../cameras.creds.json
```

`recover_creds.py` reads the `NetCamera` array (`DeviceIP`/`UserName`/`Password`/`bEnable`)
and writes a gitignored creds file in the shape the other tools consume. It prints only counts
and password **hashes**, never the values.

### 3. Build a target channel map and apply it (rearrange / resort)

Write a `target-map.json` (see `examples/target-map.example.json`): per NVR, per 1-based
channel, the camera `ip`, `lens` index, and `title`.

```
python rearrange.py --map target-map.json nvr-01 --dry-run   # preview
python rearrange.py --map target-map.json nvr-01             # apply (backs up first)
```

It writes three tables over RPC2: `RemoteDevice` (uuid-keyed partial -- IP, creds, name),
`RemoteChannel` (full list -- `Device` uuid + `Channel` lens index), `ChannelTitle` (full list
-- `Name`). Passwords are filled from your creds file because a live `getConfig` masks them.
Auth is the session-cookie method (digest fails on some firmware). The camera must already be
registered on that NVR.

### 4. Verify online + contact sheets

```
python verify.py nvr-01 --snapshots ./snaps      # readback + state + snapshot per channel
python contact_sheet.py nvr-01 --out ./sheets    # one labelled JPEG grid of all channels
```

### 5. Encode diagnosis and fixes

`diagnose_encode.py` flags the live-view-lag culprits on budget NVRs: **MJPEG main streams**
(every frame a full JPEG -- very heavy to decode), **oversized sub streams** (tiled multiview
decodes the sub; trimming it is the biggest win), and **silly mains** (e.g. 4K @ 50 fps).
Lag is usually decode load, not bandwidth.

Fixes are camera-side, backup-first and verify-after:

```
# Trim a sub to a light H.264 tile stream over ONVIF:
python fix_encode.py onvif --ip 198.51.100.20 --profile "H.264" \
    --encoding H264 --w 640 --h 480 --fps 15 --bitrate 512 --gov 30
# Drop a Dahua 4K main from 50 to 25 fps:
python fix_encode.py dahua --ip 198.51.100.30 --stream main --fps 25
# Samsung/Hanwha SUNAPI profile update:
python fix_encode.py sunapi --ip 198.51.100.40 --profile-num 2 --encoding H264 --fps 15
```

If a camera goes unreachable after an ONVIF change, `fix_encode.py` restores it from the
backup.

### 6. Known HARD limitation -- ONVIF main-stream profile selection (no fix on these NVRs)

On these NVR firmwares (fw 4.005 / 4.006 / 5.001) you **cannot select which ONVIF profile is a
channel's MAIN stream** -- neither via the RPC2 API **nor via the NVR web UI**. For legacy
cameras whose factory main profile is a firmware-locked MJPEG, you can prepare a clean H.264
profile on the camera, but the NVR keeps pulling the MJPEG one. Via the API: writing the Encode
main token is silently reverted; forcing `ServiceType=RTSP` is reset to `AUTO`; switching
`ProtocolType` to General produces a "Connected" channel with no decodable video.

**Do NOT send a future session to try the web UI expecting success** -- it was driven
end-to-end with headless automation (no plugin needed for config pages) and has **no control
for this**: the Encode page's Main Stream codec dropdown offers MJPEG only, and the device
Modify dialog (ONVIF or native Hanwha) has no main/sub profile selector. The old
"Camera > Registration > Modify/Encode > Main Stream profile" click-path does not exist on this
firmware. See `docs/METHOD.md` section 6 for the full attempted findings.

**Fix is the multiview sub-stream, which the kit already delivers:** trimming the sub to a light
H.264 tile fixes tiled live view (multiview decodes the sub). Only single-camera fullscreen
still decodes one cheap ~5 fps MJPEG main at a time. Getting an H.264 **fullscreen** main needs
a **hardware/firmware change** -- replace the MJPEG-locked cameras with H.264-primary models, or
move to a VMS/firmware that can pin the ONVIF main profile (direct General+RTSP to the H.264
profile gave undecodable video on these NVRs, so prove any such route on a non-production unit
first). Everything else (sub-stream trim, Dahua main-fps fixes) is API-applicable.

## Exporting footage / clips

This kit **manages** the NVRs; it does **not** pull recordings. To export exact MP4 clips from
the recordings (evidence footage), use **nvrclip** (https://github.com/yashau/nvrclip, credit:
yashau) — the go-to for pulling MP4 evidence clips. Do **not** reinvent RTSP dumping. It handles
Dahua **and** Hikvision, corrects recorder clock drift, stitches multi-part spans, and trims to
the exact window. Install: `go install github.com/yashau/nvrclip/cmd/nvrclip@latest` with ffmpeg
on PATH. NVR creds follow the same env/config pattern as this kit (never hardcoded). Quick shape:
`nvrclip download nvr-01 --channel front-entrance --from "YYYY-MM-DD HH:MM" --to "..."`, or
`--around "..." --minutes N`. Full install, flags, encoding modes, and bulk export are in
**`docs/footage-export.md`** — read it before exporting. nvrclip is referenced, not bundled
(upstream license unstated).

## Files

- `scripts/lib/` -- `dahua_rpc.py` (RPC2 session-cookie client), `onvif.py`, `sunapi.py`,
  `dahua_cam.py`, `config.py` (env/file credential loader).
- `scripts/` -- `survey.py`, `export_backup.py`, `decrypt_config.py`, `recover_creds.py`,
  `rearrange.py`, `verify.py`, `contact_sheet.py`, `diagnose_encode.py`, `fix_encode.py`.
- `third_party/DahuaConfigBackupDecEnc.py` -- vendored v1 decrypter (credit: bashis).
- `docs/METHOD.md` -- format/schema/limitation notes. `docs/footage-export.md` -- clip export
  via nvrclip. `examples/` -- sample configs/maps.
