# Changelog

## 1.2.2 (2026-11-04)

- The switch to download mode also finds a firmware that renamed its USB port, as long as the name has `FM-1` in it (for example "My FM-1"). Before, the name had to start with `FM-1` or `Felucca`.

## 1.2.1 (2026-11-04)

A review pass before wider use; nothing changes in what is written to the flash.

- Backups and images made under `sudo` now belong to you, not to root, so you can move or delete them.
- Clear messages instead of tracebacks: a missing libusb or pyusb, a mistyped file name, a USB drop during a read, Ctrl-C, macOS not releasing the FM-1.
- MacPorts' libusb is found; `setup.sh` finds Homebrew right after it is installed and checks the Python version; pyusb is pinned by range (1.2.1 or newer) for Python 3.8.
- `install --check` prints a complete `restore` command; step numbers in messages match the guide.
- Docs: the two chips' command sets and timings from their datasheets; the README says what a V15-over-V16 install leaves behind.

## 1.2.0 (2026-11-04)

- **`install FM-1.fwsc`**: backup, image and restore in one command, with one password and one typed `BOOT`. It saves the backup and the image, so a retry is a plain `restore`. `--check` does everything but the write.
- The guide is four steps shorter; the three separate commands stay as "Step by step instead".

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
