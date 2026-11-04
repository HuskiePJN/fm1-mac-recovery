# Firmware and chips

What the tool knows, and how well each one has been tested. "Tested" means an FM-1 was recovered with this tool and confirmed to start. Reports of new results are welcome: [open a recovery report](https://github.com/HuskiePJN/fm1-mac-recovery/issues/new/choose).

## Official firmware

| Package | Identity | `flash.bin` | Boot area (first bytes of its SHA-256) | Status |
|---|---|---|---|---|
| V15 | `FM-1_015` | `0x93000` bytes | `d9f431917776` (M-VAVE's bootloader) | **Tested** |
| V16 | `FM-1_016` | `0xA9000` bytes | `8f5228c2d6ea` (a new bootloader) | **Tested** |

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

### Which chip is in my FM-1?

Run `sudo .venv/bin/python fm1_recover.py probe` with the FM-1 in download mode. It reads nothing from the flash and prints the chip on the `Chip key` line, for example `flash 0xB36014 (UCUN UC25HQ80, tested)`. As a rough guide, the 2026 units with the M-VAVE logo on the front have the UC25HQ80.

### What differs between the two

They are interchangeable 8 Mbit (1 MiB) SPI flash chips: same memory type, same size, 4 KiB sectors and 256-byte pages. The difference that matters is the **ID** they report. The JEDEC ID is three bytes, maker, memory type and size, and only the maker byte differs:

| | Maker | Memory type | Size |
|---|---|---|---|
| Puya P25Q80H | `0x85` | `0x60` | `0x14` (1 MiB) |
| UCUN UC25HQ80 | `0xB3` | `0x60` | `0x14` (1 MiB) |

M-VAVE's own firmware (V15 and V16) runs and saves its settings on both.

Checked against the manufacturers' datasheets (UCUN UC25HQ80 v1.2, January 2022; Puya P25Q80H v1.7), everything the loader uses is the same on both:

| | Puya P25Q80H | UCUN UC25HQ80 |
|---|---|---|
| Read ID (`9Fh`) | `85 60 14` | `B3 60 14` |
| Write enable, sector erase, page program, read | `06h`, `20h` (4 KB), `02h` (256-byte page), `03h` | the same |
| Status register bits | `SRP0 BP4-BP0 WEL WIP`, `SUS1 CMP LB3-LB1 SUS2 QE SRP1` | the same |
| Sector erase time, typical / max | 8 / 20 ms | 7 / 10 ms |
| Page program time, typical / max | 2 / 3 ms | 1.5 / 3 ms |
| Endurance | 100,000 program/erase cycles | 100,000 |

The tool never erases more than one 4 KB sector at a time (no block or chip erase), never changes the status register, and waits on each command with a 10 s USB timeout, far above either chip's slowest erase. A sector whose block-protect bits were set would fail its readback check and be reported, not silently skipped.

### Why it matters

Some FM-1 software was written when only the Puya chip was known. It checks the ID, and on a UC25HQ80 it either refuses or behaves differently. At the time of writing (November 2026):

- **Custom firmware may not save.** Felucca 1.8.0 and SLOOP 2.8.4 accept only `0x856014` for saving. On a UC25HQ80 they run, but everything you save is gone at power-off ([Felucca #319](https://github.com/hugelton/Felucca/issues/319), [SLOOP #238](https://github.com/isod89/sloop-fm1/issues/238)). Some of their installers also stop on these units ([SLOOP #228](https://github.com/isod89/sloop-fm1/issues/228)).
- **Other recovery tools may refuse the unit.** MvaveFM1Unbricker accepted `0xB36014` from version 1.2.1; its Transporter script still accepts only `0x856014`.
- **M-Flasher's loader** read only blank data from a UC25HQ80 after m-bootloader had been installed. JieLi's own loader, which this tool always uses, reads and writes it normally.
- **Boot areas from custom packages.** On the UC25HQ80 unit this tool was tested on, a custom package's own boot area led to the black screen. The same firmware ran fine on M-VAVE's boot area.

For this tool, the steps are the same on both chips. It reads, erases and writes with the loader's standard commands, never relies on chip-specific features, and verifies every sector by reading it back. The chip only changes what the `Chip key` line says, and whether a write needs `--allow-untested` (it never does for these two).

If you plan to install custom firmware afterwards on a UC25HQ80, check that its release notes mention `0xB36014` or the UC25HQ80, take a full backup first, and prefer an installer that keeps M-VAVE's boot area.

## Bootloaders seen on FM-1s

| Boot area | How to reach download mode | Notes |
|---|---|---|
| M-VAVE's (V15) | From the running firmware (SysEx); no key | Restored by a V15 recovery |
| M-VAVE's (V16) | From the running firmware (SysEx); no key | Written and started with this tool; V16 sets up its settings in `0xC2000`–`0xFBFFF` on its first start |
| [m-bootloader](https://github.com/jvitkauskas/m-bootloader) | Hold REC at power-on | Replaced by a recovery |
| Generic JieLi SDK boot area from some custom packages | ROM fallback only | On a UC25HQ80 unit this gave a black screen |

## Tested recoveries

| Date | Chip | From | To | macOS | Result |
|---|---|---|---|---|---|
| 2026-11-03 | UC25HQ80 | Black screen (custom boot area and SLOOP 2.8.4) | V15 and M-VAVE's bootloader | Apple silicon | Starts; flash verified (with the script this tool grew from) |
| 2026-11-03 | UC25HQ80 | Custom firmware on M-VAVE's V15 boot area | V16 and its bootloader (169 sectors), then back to the full earlier backup (199 sectors) | Apple silicon | V16 starts and switches to download mode on request; the way back verified byte for byte, and the earlier firmware starts with its saves |

## Hardware checks of releases

| Version | Chip | Check |
|---|---|---|
| 1.0.0 | UC25HQ80 | Backup (two reads, identical); a one-sector write and verify outside the firmware, then back; a restore correctly refused when the running firmware had saved between runs |
| 1.1.0 | UC25HQ80 | V16 written with its boot area and started; `probe` from V16; a full restore of an earlier backup, boot area included |
| 1.2.0 | UC25HQ80 | `install FM-1.fwsc --check` (V16): backup, image and plan from one connection, the image byte for byte the same as `image` makes; the write path is `restore`'s, checked in 1.0.0 and 1.1.0 |
| 1.2.1 | UC25HQ80 | `install --check` again after the review pass: same plan; backup and image owned by the user who ran sudo |
