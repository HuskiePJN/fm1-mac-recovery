# FM-1 Mac Recovery

Bring a bricked **M-VAVE FM-1** with a black screen back to M-VAVE's own firmware and bootloader, using only a **Mac** and a **USB-C cable**. No Windows, no Linux, no extra hardware.

[![Offline tests](https://github.com/HuskiePJN/fm1-mac-recovery/actions/workflows/tests.yml/badge.svg)](https://github.com/HuskiePJN/fm1-mac-recovery/actions/workflows/tests.yml)

> Unofficial and not affiliated with M-VAVE. It worked on the units listed in [Firmware and chips](docs/firmware-and-chips.md). Use it at your own risk, and read [Safety](#safety) first.

## Contents

- [Is this for you?](#is-this-for-you)
- [Safety](#safety)
- [What you need](#what-you-need)
- [Step 1. Set up the Mac](#step-1-set-up-the-mac)
- [Step 2. Get the firmware file](#step-2-get-the-firmware-file)
- [Step 3. Put the FM-1 in download mode](#step-3-put-the-fm-1-in-download-mode)
- [Step 4. Back up the flash](#step-4-back-up-the-flash)
- [Step 5. Build the recovery image](#step-5-build-the-recovery-image)
- [Step 6. Write it](#step-6-write-it)
- [Step 7. Start the FM-1](#step-7-start-the-fm-1)
- [Afterwards](#afterwards)
- [Troubleshooting](#troubleshooting)
- [More](#more)

## Is this for you?

This fits if all of these are true:

- Your FM-1 stays on a black screen, or no longer starts properly, often after installing other firmware or a bootloader.
- The Mac can see it in **download mode**, a USB disk named `UBOOT1.00`. [Step 3](#step-3-put-the-fm-1-in-download-mode) shows how to get there and how to check.
- You have a Mac with macOS. It was tested on an Apple silicon Mac. Intel Macs should work but have not been tested.

Not the right guide?

- **On Windows or Linux:** use [MvaveFM1Unbricker](https://github.com/Quixotic7/MvaveFM1Unbricker).
- **Nothing ever shows up on USB, in any mode:** this cannot reach the chip. The hardware route is the [FM-1 Transporter](https://github.com/kurogedelic/FM-1-transporter).

How it works, in short: the FM-1's chip (JieLi AC791N) has a rescue mode built in that no update can erase. The tool talks to it over USB, backs up the whole 1 MB flash, puts M-VAVE's official firmware and bootloader back, and verifies every part it writes. [How it works](docs/how-it-works.md) has the details.

## Safety

- **It backs up first.** Every write starts from a backup that was read twice and compared. Nothing is written if the flash changed since.
- **Factory data stays.** The last 4 KB of the flash holds your unit's own factory data. The tool never erases or writes it, and it refuses an image from another FM-1.
- **Boot area last.** The bootloader is written last, only with `--allow-boot` and a typed `BOOT`, and only after everything else reads back correctly.
- **Nothing unconfirmed by default.** Firmware versions or flash chips nobody has confirmed yet need `--allow-untested`.

> [!WARNING]
> **The one risky moment.** Writing the boot area takes under a second. If the cable comes out or power fails right then, the USB rescue mode may stop working, and the chip then needs special hardware. Plug the FM-1 **straight into the Mac** (no hub or dock), keep the Mac on its charger, and don't touch the cable or the FM-1 while it writes.

> [!IMPORTANT]
> **Keep backups private.** A backup holds your unit's own data, including its factory data. Don't share it, and never restore someone else's.

## What you need

- A Mac with an internet connection, and your Mac password.
- A USB-C cable that carries data. Many charging cables don't.
- M-VAVE's firmware file, `FM-1.fwsc` ([step 2](#step-2-get-the-firmware-file)).
- About 30 minutes. The write itself takes 5 to 10 minutes.

| Term | Meaning |
|---|---|
| Download mode | The rescue mode built into the chip. The Mac sees it as a disk named `UBOOT1.00`. |
| Boot area | The first 16 KB of the flash (`0x0000`–`0x3FFF`), with the bootloader that starts the firmware. |
| Firmware | The FM-1's software, right after the boot area. |
| Factory sector | The last 4 KB (`0xFF000` and up), unique to each unit. Never touched. |

## Step 1. Set up the Mac

1. Download this repository: the green **Code** button, then **Download ZIP**. Unzip it, rename the folder from `fm1-mac-recovery-main` to `fm1-mac-recovery`, and move it to your home folder (the one with your name, next to Desktop and Documents).
2. Open **Terminal** (Applications, then Utilities, then Terminal).
3. Install Apple's command line tools. If they are already there, Terminal says so.

   ```sh
   xcode-select --install
   ```

4. Install [Homebrew](https://brew.sh) if you don't have it (one command on its home page).
5. Go to the folder and run the setup. It installs `libusb` and `pyusb`, and downloads JieLi's flash loader from [jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool), checking its fingerprint.

   ```sh
   cd ~/fm1-mac-recovery
   sh setup.sh
   ```

Every command below runs in this folder. If you open a new Terminal window, run `cd ~/fm1-mac-recovery` first.

## Step 2. Get the firmware file

Put M-VAVE's official firmware in the folder, named `FM-1.fwsc`. The tool checks which version it is in step 5. M-VAVE's firmware is never included here.

| File | Status |
|---|---|
| **V15** (`FM-1_015`) | **Tested.** M-VAVE's site no longer offers it, so use a copy you saved earlier. |
| **Your own backup** from before the problem | **Best of all**, if you made a full flash backup while the FM-1 still worked (with this tool, M-Flasher or MvaveFM1Unbricker). Skip step 5 and use that backup as the image in step 6. |
| **V16** (`FM-1_016`) | **Recognised, not yet tested.** This is what M-VAVE's [FM-1 page](https://www.m-vave.com/product?id=fm-1) offers now. It needs `--allow-untested`. |

> [!NOTE]
> **Firmware note: V16.** V16 brings its own new bootloader, and its firmware is larger, running up to `0xA8FFF`, where V15 keeps its settings. The tool recognises the official V16 file, but nobody has recovered an FM-1 with it yet. If you have V15, recover with V15, then update to V16 the normal way. If you try V16, please [report how it went](https://github.com/HuskiePJN/fm1-mac-recovery/issues/new/choose).

## Step 3. Put the FM-1 in download mode

Connect the FM-1 straight to the Mac, then use the row that fits:

| Your FM-1 | What to do |
|---|---|
| Still starts a firmware (the screen works) | Nothing yet. The tool asks the firmware to switch by itself in steps 4 and 6. This works with M-VAVE's firmware and Felucca-family firmware (Felucca, SLOOP and builds based on them). |
| Black screen, with [m-bootloader](https://github.com/jvitkauskas/m-bootloader) installed | Switch it off. Hold **REC** while you switch it on, and let go after 2 seconds. |
| Black screen, anything else | Try in order, checking after each: (1) leave it on for two full minutes; (2) switch off, hold **OCT−** and **OCT+**, switch on and keep holding for 10 seconds; (3) three quick restarts: on, wait 10 s, off; twice, then on. |

> [!NOTE]
> **Bootloader note.** The black-screen tips come from MvaveFM1Unbricker. They work when a Felucca-family firmware's safety code still runs (a watchdog and a boot-loop guard). M-VAVE's own bootloader has no key for download mode; m-bootloader adds the REC key.

Check that the Mac sees it. A line with `UBOOT` means it is in download mode:

```sh
ioreg -p IOUSB | grep -i uboot
```

macOS may say the disk is not readable. Click **Ignore**, never **Initialize**. Download mode can time out after a few minutes; if a step can't find the FM-1, put it in download mode again and repeat that step.

## Step 4. Back up the flash

```sh
sudo .venv/bin/python fm1_recover.py backup
```

Type your Mac password (nothing shows while you type). If macOS asks to allow access to a removable volume, allow it. It takes about a minute:

```text
Device      WL82 UBOOT1.00
Loader      JieLi wl82 at 0x01C02000
Chip key    0x980F   flash 0xB36014 (UCUN UC25HQ80, tested)
Reading 1/2 100%
Reading 2/2 100%
Backup      backups/fm1-YYYYMMDD-HHMMSS.bin
```

It ends with the exact command for step 5. Copy the `backups` folder somewhere safe, such as an external drive.

> [!NOTE]
> **Flash chip note.** FM-1s use one of two 1 MB flash chips: `0x856014` (Puya P25Q80H) or `0xB36014` (UCUN UC25HQ80, in the 2026 units with the logo on the front). The UC25HQ80 was recovered with this tool; the Puya is read by the same loader and expected to work. The tool uses JieLi's own loader because, on a UC25HQ80 after m-bootloader, M-Flasher's loader read only blank data. Any other chip key or flash size stops the tool before it touches anything. Why the chip matters for custom firmware and other tools: [Firmware and chips](docs/firmware-and-chips.md#why-it-matters).

## Step 5. Build the recovery image

This runs on the Mac only. It puts M-VAVE's boot area and firmware over your backup, so your settings area and factory data stay your own. Use the command step 4 printed, or replace the backup name:

```sh
.venv/bin/python fm1_recover.py image FM-1.fwsc --current backups/fm1-YYYYMMDD-HHMMSS.bin -o recovery.bin
```

```text
Package     FM-1_015, flash.bin 0x93000 bytes: official V15 (tested)
Image       recovery.bin: package 0x0-0x92FFF, the rest from the backup
```

If it says `NOT a known official package`, stop: that file is not M-VAVE's original V15 or V16.

## Step 6. Write it

Use the command step 5 printed, or:

```sh
sudo caffeinate -i .venv/bin/python fm1_recover.py restore recovery.bin --current backups/fm1-YYYYMMDD-HHMMSS.bin --allow-boot
```

1. It lists the 4 KB sectors that will change. The boot area sectors `00000 01000 02000 03000` come **last**. `FF000` is never listed.
2. It asks you to type `BOOT` if the boot area changes, or `WRITE` if it doesn't. Nothing is written before that.
3. It connects, checks that the flash still matches your backup, and writes the firmware.
4. It reads everything back, then writes the boot area, then checks the whole flash once more.

```text
Verifying   100%
Done: flash matches the image (factory sector unchanged).
Unplug USB, switch the FM-1 off, wait 5 s, switch it on.
```

> [!NOTE]
> **Boot area note.** Asked to type `BOOT`: your boot area is being put back to M-VAVE's original, which is usual after m-bootloader or a custom package with its own boot area (m-bootloader's REC key goes away). Asked to type `WRITE`: your boot area already matches and isn't touched.

Short USB hiccups are retried by themselves. If the FM-1 drops off USB, the tool waits for it, reconnects and writes that part again. `caffeinate` keeps the Mac awake.

## Step 7. Start the FM-1

Unplug the cable, switch the FM-1 off, wait 5 seconds and switch it on without holding any key. It should start M-VAVE's firmware.

## Afterwards

- **Updating to V16:** once V15 runs, update with M-VAVE's own updater as usual.
- **Download mode later:** M-VAVE's bootloader has no key for it. While a firmware runs, `backup` and `restore` ask for it by themselves; [M-Flasher](https://github.com/jvitkauskas/m-flasher)'s **Download mode** button does the same.
- **Odd settings or sounds after custom firmware:** custom data may remain in the settings area. A factory reset in M-VAVE's firmware may fix it. MvaveFM1Unbricker's `repair-settings` handles this on Windows and Linux.

> [!NOTE]
> **Custom firmware note, for UC25HQ80 units.** Some custom firmware was written for the Puya chip and, at the time of writing, may run on a UC25HQ80 without saving anything. On the unit this was tested on, a custom package's own boot area caused the black screen, while its firmware ran fine on M-VAVE's boot area. Prefer installers that keep M-VAVE's boot area, and take a full backup first.

## Troubleshooting

| Message | What it means and what to do |
|---|---|
| `No FM-1 in download mode` | It isn't in download mode, or it timed out. Repeat step 3 and check with `ioreg`. Try another cable, straight into the Mac. |
| `macOS did not release the FM-1` | Run it from Terminal with `sudo`. If asked, allow access to removable volumes in System Settings, Privacy & Security. |
| `loader/wl82loader.bin is missing` | Run `sh setup.sh` again. |
| `NOT a known official package` | The firmware file isn't M-VAVE's original V15 or V16. Download it from M-VAVE again. |
| `has not been confirmed with this tool yet` | That firmware or chip is untested. Use a tested one, or add `--allow-untested` at your own risk. |
| `looks like it comes from another FM-1` | The image's factory sector isn't yours. Build the image from your own backup (step 5). |
| `the flash no longer equals …` | Nothing was written. Take a new backup (step 4) and use it in steps 5 and 6. |
| `Firmware readback differs: boot area NOT written` | Your bootloader wasn't touched, so download mode still works. Repeat steps 3 to 6. |
| `Do NOT power off` | Leave the FM-1 on and connected. Run step 6 again; if it asks, take a new backup first. |
| `Unexpected chip key or flash size` | Not a chip the tool knows. It stopped before touching anything. Please [open an issue](https://github.com/HuskiePJN/fm1-mac-recovery/issues/new/choose) with the line it printed. |

## More

- [How it works](docs/how-it-works.md): the flash layout, the USB protocol and the safety design.
- [Firmware and chips](docs/firmware-and-chips.md): what has been tested, and what hasn't.
- [Adding support](docs/adding-support.md): how a new firmware version or flash chip gets added.
- [Changelog](CHANGELOG.md)
- Offline tests, no FM-1 needed: `python3 -m unittest discover tests`

## Credits

- [jl-uboot-tool](https://github.com/kagaimiq/jl-uboot-tool) (kagaimiq): the JieLi protocol and the flash loader.
- [M-Flasher](https://github.com/jvitkauskas/m-flasher) and [m-bootloader](https://github.com/jvitkauskas/m-bootloader) (jvitkauskas): the macOS USB approach and the protocol specification.
- [MvaveFM1Unbricker](https://github.com/Quixotic7/MvaveFM1Unbricker) (Quixotic7): the FM-1 flash layout, the V15 reference and the download-mode tips.

MIT licence, see [LICENSE](LICENSE). M-VAVE and FM-1 are trademarks of their owners. The firmware is M-VAVE's: get it from them.
