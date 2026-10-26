# Footage / clip export (via nvrclip)

This kit (`dahua-nvr-kit`) covers **configuring and managing** the NVRs — surveying channels,
recovering camera credentials, rearranging/retitling channels, and tuning encode profiles. It
does **not** pull recordings off the recorder.

For **exporting exact MP4 clips** from NVR recordings (evidence clips, incident footage), the
recommended companion tool is **[nvrclip](https://github.com/yashau/nvrclip)** by **yashau** — a
lightweight Go CLI that searches an NVR's stored recordings and produces trimmed MP4 files. Reach
for it instead of hand-rolling RTSP dumps: it talks to the recorder's search/download API,
stitches multi-part spans, corrects the recorder's clock drift, and trims to the exact window you
ask for.

> nvrclip is a **separate upstream project**, referenced here — **not** bundled in this repo. See
> "License / status" below before redistributing it.

## What it does

- Searches the NVR's own recording index and downloads the covering segment(s), then produces a
  single MP4 for the requested time window.
- Supports **Dahua** (raw CGI segment search, indexed-file preservation, keyframe detection,
  timestamp-based trimming) **and Hikvision** (ISAPI `ContentMgmt/search`, HTTP(S) download,
  local offset-trimming, multi-part concatenation).
- **Clock correction**: by default it treats the PC clock as the reference and corrects for the
  recorder's clock error when selecting the window (disable per-command with `--no-time-offset`,
  or per-NVR with `auto_time_offset = false`).
- **Multi-part spans**: a window crossing multiple recorded files is concatenated into one clip.
- **Timestamp trim**: the output is trimmed to the exact `--from`/`--to` (or centered) window.

## Install

nvrclip is written in **Go** (go.mod requires a recent Go toolchain — 1.26.x at time of writing)
and needs **ffmpeg on PATH**.

```
# build/install from source
go install github.com/yashau/nvrclip/cmd/nvrclip@latest

# ffmpeg (required; example on Windows)
winget install --id Gyan.FFmpeg
```

Prebuilt release binaries are not consistently published upstream — check the repo's Releases
page, otherwise build from source as above. You can also clone and run
`go run ./tools/build --version <v>` to produce a local binary. Runs on Windows, macOS, Linux.

## Credentials (same pattern as the rest of this kit)

NVR admin credentials are supplied via config file or environment — **never hardcoded**. nvrclip
reads an `nvrclip.toml` where each NVR's password is either `password = "..."` or, preferred, an
env reference `password_env = "NVRCLIP_<NVR>_PASSWORD"`. This mirrors this kit's own
env/config-file credential rule (`NVR_PASSWORD` / gitignored `config.json`).

## Usage

All examples below use RFC 5737 documentation IPs and placeholder channel aliases — substitute
your own NVR names, channel aliases/IDs, and timestamps.

### `grab` — channel by alias across all configured NVRs

```
nvrclip grab "front-entrance" --from "2026-05-05 14:00" --to "2026-05-05 14:10"
```

### `download` — explicit NVR + channel, exact window

```
nvrclip download nvr-01 --channel front-entrance \
    --from "2026-05-05 14:00" --to "2026-05-05 14:10"
```

`--channel` accepts an alias or a 1-based numeric ID.

### Centered window with `--around` / `--minutes`

```
# ±5 minutes around a point in time
nvrclip download nvr-01 --channel 3 --around "2026-05-05 14:05" --minutes 10
```

### Encoding mode — stream-copy vs re-encode

- **`--format copy`** (default): stream-copy, no re-encode — fast, but cuts land on keyframes.
- **`--format exact`**: H.264 **re-encode** for precise cuts when stream-copy boundaries aren't
  tight enough, and to normalize multi-part joins. Slower and lossy; use only when you need the
  exact frame.

Other useful flags: `--download-only` (fetch segments, skip final MP4), `--keep-temp` (keep
intermediate files), `--no-time-offset` (disable clock correction for this run).

### Bulk / multi-day export (resumable)

For exporting a daily window across a date range, nvrclip ships `bulk-export.ps1`, which chunks
the range into pieces and **supports resume** (re-run to pick up where it stopped):

```
./bulk-export.ps1 -Nvr nvr-01 -Channel 1 -StartDate "2026-05-01" -EndDate "2026-05-05" `
  -DailyFrom "08:00" -DailyTo "19:00" -ChunkMinutes 180 -OutRoot "./export" -Detach
```

## License / status

As of this writing nvrclip has **no LICENSE file and no stated license** in its repository — its
license is **unstated upstream**. That is why this kit only **references and links** nvrclip
(credit: **yashau**, https://github.com/yashau/nvrclip) rather than vendoring or redistributing
its code. If you intend to redistribute nvrclip or its binaries, check the upstream license
situation first. This kit's own MIT license covers only this kit's code.
