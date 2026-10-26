# third_party

## DahuaConfigBackupDecEnc.py

Vendored, unmodified, from **bashis** (`mcw <mcw noemail eu>`, 2021), with contributions by
iTuneDVR (2023, XVR support). It decrypts/encrypts Dahua config backups (the `MWPZWJGS` /
`DHRDENFR` format, "v1": base64 + AES-ECB wrapping a gzip of the config tree, with an MD5
integrity check).

`scripts/decrypt_config.py --mode v1` shells out to this file. The v2 (AES stream-cipher)
best-effort path in `decrypt_config.py` is original to this kit.

The original project and licensing terms are bashis'. This copy preserves the author header
and demo notes in the file. If you redistribute, keep that attribution intact. Upstream:
`DahuaConfigBackupDecEnc` by bashis (search "DahuaConsole" / "mcw0" on GitHub).

This kit's own MIT license (see ../LICENSE) covers only the kit's own code, not this vendored
file.

## Related tools (referenced, not bundled)

### nvrclip

**[nvrclip](https://github.com/yashau/nvrclip)** by **yashau** is the recommended companion tool
for **exporting MP4 clips** from NVR recordings (Dahua + Hikvision). This kit configures/manages
the NVRs; nvrclip pulls the footage. See `../docs/footage-export.md` for install and usage.

nvrclip is **not vendored** into this repo — only referenced and linked. Its upstream repository
has **no LICENSE file and no stated license**, so its license is **unstated upstream**; check
with the author before redistributing nvrclip or its binaries. Because we only reference (not
bundle) it, nothing of nvrclip is shipped under this kit's MIT license.
