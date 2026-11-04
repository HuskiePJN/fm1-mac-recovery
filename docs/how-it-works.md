# How it works

## The chip and its download mode

The FM-1 runs on a JieLi AC791N (WL82 family). Its mask ROM holds a USB download mode that no firmware update can erase. In that mode the chip appears as a USB mass-storage device, vendor `4C4A`, product `8057`, named `WL82 UBOOT1.00`. JieLi's tools speak their own commands to it through SCSI command blocks.

The chip gets there in one of these ways:

- A running firmware receives the SysEx `F0 22 24 35 7D F7` and restarts into it. M-VAVE's firmware and Felucca-family firmware both do this. `dlmode.swift` sends it through CoreMIDI.
- m-bootloader enters it when REC is held at power-on.
- The ROM falls back to it when the boot chain fails in certain ways, for example after a Felucca-family boot-loop guard gives up.

## What the tool does

1. **Connects** with libusb as root. macOS's disk driver holds the device, so the tool detaches it, as M-Flasher does.
2. **Uploads JieLi's flash loader** (`wl82loader.bin`, from jl-uboot-tool, already in the ROM's upload format) into RAM at `0x01C02000` and starts it. The tool checks the loader's SHA-256 first.
3. **Identifies the chip.** The chip key must be `0x980F`, and the flash must be 1 MiB (JEDEC ID ending in `0x14`). Otherwise it stops.
4. **Reads** the whole flash twice. The two reads must be identical before a backup is saved.
5. **Builds an image** offline: the package's `flash.bin` (boot area and firmware) over the backup. Everything after the firmware (settings areas and the factory sector) stays the unit's own.
6. **Writes** only the 4 KiB sectors that differ, each erased, programmed and read back, with up to four tries. The boot area goes last.
7. **Verifies** the whole flash at the end. The factory sector must be unchanged.

## Flash layout (V15)

| Range | What |
|---|---|
| `0x00000`–`0x03FFF` | Boot area: bootloader, its record and configuration |
| `0x04000`–`0x92FFF` | Firmware (V15) |
| `0x93000`–`0xFEFFF` | Settings, presets and other data |
| `0xFF000`–`0xFFFFF` | Factory sector, unique to each unit: never written |

V16's firmware runs to `0xA8FFF`. Custom firmware uses its own layout after the firmware area.

## The `.fwsc` package

An M-VAVE package starts with 20 blocks of 48 bytes. The 48th byte of each block spells the identity (`FM-1_015` for V15). After unwrapping, a JieLi UFW header (XOR-ciphered with a CRC16 keystream, key `0xFFFF`) lists the files. Entry type 0 is `flash.bin`, the image from flash address 0. The tool recognises an official package by its identity, its size and the SHA-256 of `flash.bin` from `0x4000` to the end.

## The safety design

- **Offline first.** `image` and the plan in `restore` need no device. The typed confirmation comes before the tool takes the FM-1, so the unit never waits in download mode while you read. `install` asks for it before it connects for the same reason, then takes the backup, builds the image and writes in one connection; it saves both files, so a retry is a plain `restore`.
- **The flash must still equal your backup.** `restore` reads the whole flash before writing. If it changed, it stops without writing.
- **The same unit.** An image whose factory sector differs from the backup's is refused.
- **The boot area last.** Before the first boot sector, the tool reads back the whole firmware area. If anything differs, it stops with the old bootloader intact, so download mode still works. The four boot sectors are then written without a pause.
- **Unconfirmed means opt-in.** Firmware marked untested, or a flash chip not in the table, needs `--allow-untested`.
- **The factory sector is out of reach.** `write_sector` refuses any address at or above `0xFF000`.

## Commands

| Command | Device | Writes |
|---|---|---|
| `install PKG [--check]` | yes | the backup and the image on the Mac, then the sectors that differ (nothing with `--check`) |
| `probe` | yes | nothing |
| `backup` | yes | `backups/fm1-DATE.bin` on the Mac |
| `image PKG --current BACKUP -o OUT` | no | `OUT` on the Mac |
| `restore IMAGE --current BACKUP [--allow-boot]` | yes | the sectors that differ |

Options: `--keep-boot` (image: keep the boot area from the backup), `--allow-untested`, `--version`.
