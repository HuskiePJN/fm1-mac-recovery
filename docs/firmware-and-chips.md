# Firmware and chips

What the tool knows, and how well each one has been tested. "Tested" means an FM-1 was recovered with this tool and confirmed to start. Reports of new results are welcome: [open a recovery report](https://github.com/HuskiePJN/fm1-mac-recovery/issues/new/choose).

## Official firmware

| Package | Identity | `flash.bin` | Boot area (first bytes of its SHA-256) | Status |
|---|---|---|---|---|
| V15 | `FM-1_015` | `0x93000` bytes | `d9f431917776` (M-VAVE's bootloader) | **Tested** |
| V16 | `FM-1_016` | `0xA9000` bytes | `8f5228c2d6ea` (a new bootloader) | **Recognised, not yet tested**, needs `--allow-untested` |

The tool checks the SHA-256 of `flash.bin` from `0x4000` to its end:

- V15: `6edf3c37fb5bbbc33607c89375ee024d5477c17914d72221c8c68e58a8255686`
- V16: `c47d8895963c070f9334efd6a617d7aae5daf8480ffcf3438ffb634c03de8ef7`

The whole V15 file has SHA-256 `db1642b2b6fa5c2cccb11ffd13878068bb28601678d3644049f99dc40e7edb8a`. The V16 file served by M-VAVE on 21 October 2026 has `d017fb65e70aca97ee29d944470c3515a74581df5c0576bf70de917c7b2b61d5`.

M-VAVE's site offers only the newest version. This repository never includes their firmware.

## Flash chips

| JEDEC ID | Chip | Where | Status |
|---|---|---|---|
| `0xB36014` | UCUN UC25HQ80 | 2026 units with the logo on the front | **Tested** |
| `0x856014` | Puya P25Q80H | Earlier units | **Expected**: read by the same loader, not yet confirmed with this tool |

Any other 1 MiB chip is reported as unknown. Backups still work; writing needs `--allow-untested`. A chip that isn't 1 MiB, or a chip key other than `0x980F`, stops the tool.

## Bootloaders seen on FM-1s

| Boot area | How to reach download mode | Notes |
|---|---|---|
| M-VAVE's (V15) | From the running firmware (SysEx); no key | Restored by a V15 recovery |
| M-VAVE's (V16) | Not yet known | Comes with V16 |
| [m-bootloader](https://github.com/jvitkauskas/m-bootloader) | Hold REC at power-on | Replaced by a recovery |
| Generic JieLi SDK boot area from some custom packages | ROM fallback only | On a UC25HQ80 unit this gave a black screen |

## Tested recoveries

| Date | Chip | From | To | macOS | Result |
|---|---|---|---|---|---|
| 2026-11-03 | UC25HQ80 | Black screen (custom boot area and SLOOP 2.8.4) | V15 and M-VAVE's bootloader | Apple silicon | Starts; flash verified (with the script this tool grew from) |

## Hardware checks of releases

| Version | Chip | Check |
|---|---|---|
| 1.0.0 | UC25HQ80 | Backup (two reads, identical); a one-sector write and verify outside the firmware, then back; a restore correctly refused when the running firmware had saved between runs |
