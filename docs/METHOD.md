# METHOD -- how the kit works

Technical notes behind the scripts. Everything here concerns NVRs/cameras you own or are
authorized to administer.

## 1. RPC2 login (session-cookie auth)

Dahua NVRs/DVRs/IP cameras expose a JSON-RPC API at `/RPC2`, with login at `/RPC2_Login`.
Auth is a two-step MD5 challenge-response:

1. `POST /RPC2_Login` `global.login` with an empty password. The server replies with
   `params.realm`, `params.random`, a `session` id, and `params.encryption` (expect
   `Default`).
2. Compute `hash = MD5( user : random : MD5( user : realm : password ) )`, uppercase hex.
   `POST global.login` again with that hash, the session id, and `authorityType: "Default"`.

After login, set the session id as the **`DhWebClientSessionID` cookie** and reuse the
session for all calls. This matters: on several firmware builds HTTP Digest auth against the
CGI endpoints fails, while the cookie-based RPC2 session works. So we authenticate once over
RPC2 and ride that cookie (including for `snapshot.cgi` and `configFileExport.backup`).

**Do not loop on a failed login.** Dahua locks the admin account after a few bad attempts.
`DahuaRPC.login()` makes exactly one attempt and raises on failure.

Useful methods:

- `configManager.getConfig` / `setConfig` -- read/write named config tables.
- `LogicDeviceManager.getCameraState {uniqueChannels:[-1]}` -> `states[].{channel,
  connectionState}` (channel is zero-based).

## 2. Config-backup export + decrypt -> recover camera credentials

An NVR stores the credentials it uses to pull each attached camera. If those camera passwords
are lost but the NVR still has them, export and decrypt the NVR config.

- Export: `GET /cgi-bin/configFileExport.backup?action=All&ExtensionName=0` (try `0` and `1`).
  Output begins with magic `MWPZWJGS` (or `DHRDENFR` on some VTH exports).
- Decrypt, **v1** (common NVR/XVR form): after the 8-byte magic + 1 version byte, the body is
  base64 -> **AES-ECB** -> a small header (`version`, `size`, trailing MD5) wrapping a **gzip**
  (`.tgz`) of the config tree. The AES key is derived from a device-class string via Dahua's
  obfuscation:
  - XOR each char of the class string with its 1-based position, then MD5-hex.
  - `nvr` -> obfuscate `DahuaNVR`; `xvr` -> obfuscate `DahuaHCVR`; cameras use the device
    HWID/model string.
  This path is handled by the vendored `third_party/DahuaConfigBackupDecEnc.py` (credit:
  bashis). `scripts/decrypt_config.py --mode v1 --key nvr` wraps it and verifies the MD5.
- Decrypt, **v2** (seen on some newer firmware): same magic, but the body is an AES **stream
  cipher** (OFB) instead of ECB-over-base64. `decrypt_config.py --mode v2` tries candidate
  keys/IVs (header IV at bytes 9..25, obfuscated class keys) and reports which yields a gzip
  stream. Best-effort; extend the candidate list per firmware.
- Recover: the decrypted tree's `Config/Config1` is JSON with a `NetCamera` array; each entry
  has `DeviceIP`, `UserName`, `Password`, `bEnable`. `recover_creds.py` harvests the enabled
  ones into a gitignored `cameras.creds.json`.

## 3. Build a target channel map and apply it (rearrange / resort)

Three config tables define the channel layout:

- **`RemoteDevice`** -- a **uuid-keyed** dict. Each entry is a camera connection:
  `Address`, `Port`, `ProtocolType`, `UserName`, `Password`, `Enable`,
  `VideoInputs[0].Name` (the camera-side name), etc. Send a **partial** table with only the
  uuids you touch.
- **`RemoteChannel`** -- a **list**; entry *i* binds channel *i+1*:
  `Device` (the RemoteDevice uuid), `Channel` (lens/stream index, 0 for single-lens),
  `Enable`, `BufDelay`. Send the **full** list.
- **`ChannelTitle`** -- a **list**; entry *i* is channel *i+1*'s on-screen `Name`. Full list.

To put camera X on channel N: find X's existing RemoteDevice uuid (reuse it -- the camera must
already be registered), set `RemoteChannel[N-1].Device = uuid` and `.Channel = lens`, and set
`ChannelTitle[N-1].Name`. Fill `Password` from your recovered creds, because a live
`getConfig` returns the password **masked** (all `*`); writing the masked value back would
break the connection.

`rearrange.py` does this from a `target-map.json`, backing up the three tables first.

## 4. Verify

- Read back `RemoteDevice`/`RemoteChannel`/`ChannelTitle` and `getCameraState`; confirm each
  channel binds the intended IP and reports `Connected`.
- `GET /cgi-bin/snapshot.cgi?channel=N` returns a JPEG -- proof of real video, not just
  reachability. `contact_sheet.py` tiles these into one labelled image.

## 5. Encode diagnosis + fixes

Read `configManager.getConfig name=Encode` (text form:
`table.Encode[ch].MainFormat[0].Video.*` and `...ExtraFormat[0]...`). Live-view lag on budget
NVRs is usually **decode load**, not bandwidth:

- **MJPEG main streams** -- no inter-frame compression; every frame a full JPEG. A handful of
  these decoded at once for tiled live view will choke the NVR.
- **Oversized sub streams** -- tiled multiview decodes the **sub**. A SXGA/1080p 25-30 fps sub
  (or a sub larger than the main) defeats the point. Trimming the sub is the biggest tiled-view
  win.
- **Silly mains** -- e.g. 4K @ 50 fps, or absurd bitrates.

`diagnose_encode.py` flags these and estimates a per-channel pixels/sec decode budget.

Fixes are **camera-side** (`fix_encode.py`), backup-first and verify-after:

- **ONVIF** `SetVideoEncoderConfiguration` -- change a profile's codec/resolution/fps/bitrate/
  GOP. Raw SOAP + WS-Security `UsernameToken` `PasswordDigest`; no heavyweight SOAP stack.
- **Hanwha/Samsung SUNAPI** (`/stw-cgi/media.cgi?msubmenu=videoprofile&action=update`) -- for
  cameras whose profiles are easier to drive over SUNAPI.
- **Dahua Encode CGI** (`configManager.cgi?action=setConfig&Encode[...]`) -- tune a Dahua
  camera's main/sub directly.

## 6. Known limitation -- ONVIF main-stream profile selection is NOT exposed to the API

On the NVR firmware this kit was built against, you **cannot** choose which ONVIF profile the
NVR subscribes to as a channel's **main** stream via the RPC2 API. This matters for legacy
cameras (e.g. some Samsung/Hanwha models) whose factory **main** profile is MJPEG and is
firmware-locked on the camera -- you can prepare a clean H.264 profile on the camera, but the
NVR keeps pulling the MJPEG one as main.

What was tried (each applied to one pilot channel, then reverted), all failed:

1. **Write `Encode.MainFormat[0]` profile token** to the H.264 profile: `setConfig` returns
   `result=true` but is **silently ignored** -- for an ONVIF device the NVR re-derives the main
   profile from the camera and reverts the token.
2. **`RemoteDevice` `ServiceType=RTSP` + explicit `MainStreamUrl`** to the H.264 profile: the
   NVR **forces `ServiceType` back to `AUTO`** and auto-picks the camera's first profile.
3. **Switch `ProtocolType` Onvif -> General (raw RTSP)** with explicit main/sub URLs:
   `setConfig` sticks and the channel reports `Connected`, but **no decodable video** --
   `snapshot.cgi` returns HTTP 500 on both streams and the NVR stops mirroring encode.
   ("Connected" was only reachability.) Reverting to Onvif restored video immediately.

No other config holds the mapping (`RemoteChannel` has only `{BufDelay, Channel, Device,
Enable}`); candidate methods like `getRemoteDeviceStreamCaps`, `getDeviceProfiles`,
`RemoteDevice.getProfiles` return Method-not-found.

**Do it in the local web/monitor UI**, which exposes an ONVIF main/sub profile picker the API
does not:

> Camera (Registration) -> select the device -> Modify / Encode -> set **Main Stream profile**
> to the desired H.264 profile (keep **Sub Stream** on the light H.264 profile) -> Save.

Repeat per affected channel. Everything else (sub-stream trim, Dahua main-fps fixes) is already
API-applicable, so only the main-stream profile swap for firmware-locked-MJPEG cameras needs
the UI.
