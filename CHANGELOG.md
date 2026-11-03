# Changelog

## 1.1.0 (2026-11-03)

- **V16 is tested.** An FM-1 was taken to V16 with its new bootloader, started, switched to download mode from V16, and restored back. V16 no longer needs `--allow-untested`, and the guide now starts from the V16 file M-VAVE offers.
- Docs: what V16 changes in the flash, and that going back is best done by restoring a backup.
- Docs: the two flash chips, how to tell which one you have, what differs and why it matters.

## 1.0.0 (2026-11-03)

First public release.

- `backup`, `image` and `restore` for the M-VAVE FM-1 on macOS, over the chip's USB download mode, with JieLi's own flash loader.
- Recognises official V15 (tested) and V16 (not yet tested; needs `--allow-untested`).
- Knows the UCUN UC25HQ80 (tested) and Puya P25Q80H (expected) flash chips.
- Asks a running firmware to switch to download mode by itself (`dlmode.swift`).
- Refuses images from another FM-1, never writes the factory sector, and writes the boot area last.
- Prints the next command after each step.
- `setup.sh` for a one-command setup, and offline tests that need no FM-1.
