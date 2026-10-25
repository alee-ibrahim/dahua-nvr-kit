# Sample contact-sheet description

`contact_sheet.py nvr-01 --out ./sheets` produces a single JPEG: a 4-wide grid of the NVR's
channel snapshots, each tile with a caption bar. No real image is shipped in this repo; this
is what a sheet looks like, described:

```
+--------------------------+--------------------------+--------------------------+--------------------------+
| ch01 198.51.100.20 L0    | ch02 198.51.100.21 L0    | ch03 198.51.100.22 L0    | ch04 198.51.100.23 L0    |
| [Connected] Main Entrance| [Connected] Lobby        | [Connected] Rear Door    | [Connected] Parking A    |
|   <live snapshot>        |   <live snapshot>        |   <live snapshot>        |   <live snapshot>        |
+--------------------------+--------------------------+--------------------------+--------------------------+
| ch05 ...                 | ...                      | ...                      | ...                      |
```

- Caption colour is green when the channel reports `Connected`, reddish otherwise.
- A tile with no snapshot (camera unreachable / stream unavailable) shows the caption over a
  dark background.
- Use it right after `rearrange.py` to confirm each channel shows the intended camera in the
  intended order.
