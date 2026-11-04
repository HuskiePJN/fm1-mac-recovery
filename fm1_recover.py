#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""FM-1 Mac Recovery: back up and restore an M-VAVE FM-1 over the chip's USB download mode.

The FM-1's chip (JieLi AC791N, ROM "WL82 UBOOT1.00") has a download mode in its mask ROM. This
tool talks to it over USB with libusb, uploads JieLi's flash loader (loader/wl82loader.bin, from
jl-uboot-tool) into RAM, and reads or writes the 1 MiB flash with it.

  sudo caffeinate -i .venv/bin/python fm1_recover.py install FM-1.fwsc      (backup, image and restore in one go)

or step by step, to look at the image before anything is written:
  sudo .venv/bin/python fm1_recover.py backup
  .venv/bin/python fm1_recover.py image FM-1.fwsc --current backups/BACKUP.bin -o recovery.bin
  sudo caffeinate -i .venv/bin/python fm1_recover.py restore recovery.bin --current backups/BACKUP.bin --allow-boot

Safety: the factory sector (0xFF000 and up) is never erased or written. Every restore checks that
the flash still equals the backup you name, writes only the 4 KiB sectors that differ, writes the
boot area (0x0000-0x3FFF) last and only with --allow-boot and a typed BOOT, and verifies every
sector and the whole flash. Firmware and flash chips that nobody has confirmed yet need
--allow-untested. See README.md and docs/.
"""
import argparse
import hashlib
import os
import shlex
import subprocess
import sys
import time
import zlib
from pathlib import Path

__version__ = "1.2.2"

HERE = Path(__file__).resolve().parent
VID, PID = 0x4C4A, 0x8057       # JieLi ROM download mode
CHIP_KEY = 0x980F               # every FM-1 seen so far (AC791N)
FLASH = 0x100000                # 1 MiB
FACTORY = 0xFF000               # last sector: the unit's own factory data, never touched
BOOT_END = 0x4000               # boot area: bootloader, its record and configuration
SECTOR = 0x1000
TIMEOUT = 10000
LOADER = (0x01C02000, "wl82loader.bin", "d41da6126760c9d66660bcc0cac8d27d221806c5e369a8036921efe68dca5376")

# ---- What is known. New firmware versions and flash chips are added here (docs/adding-support.md).
# Official packages: identity -> name, end of flash.bin, sha256 of 0x4000 to that end, tested, note.
FIRMWARE = {
    "FM-1_015": ("V15", 0x93000, "6edf3c37fb5bbbc33607c89375ee024d5477c17914d72221c8c68e58a8255686", True,
                 "restores M-VAVE's bootloader (boot area sha256 d9f431917776...)"),
    "FM-1_016": ("V16", 0xA9000, "c47d8895963c070f9334efd6a617d7aae5daf8480ffcf3438ffb634c03de8ef7", True,
                 "has its own new bootloader (8f5228c2d6ea...) and a larger firmware, to 0xA8FFF"),
}
# Flash chips: JEDEC ID -> name, status. "tested": recovered with this tool. "expected": used in FM-1s
# and read by the same loader, not yet confirmed here. Any other 1 MiB chip needs --allow-untested to write.
CHIPS = {
    0xB36014: ("UCUN UC25HQ80", "tested"),
    0x856014: ("Puya P25Q80H", "expected"),
}

MAGIC = bytes([0xC3, 0xCF, 0xC0, 0xE8, 0xCE, 0xD2, 0xB0, 0xAE, 0xC4, 0xE3, 0xA3, 0xAC, 0xD3, 0xF1, 0xC1, 0xD6])


def crc16(data, c=0):
    """CRC16/XMODEM (poly 0x1021)."""
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else c << 1
        c &= 0xFFFF
    return c


def crc_cipher(data, key=0xFFFFFFFF):
    """JieLi's CrcDecode stream (the chip-key reply)."""
    c = crc16((key >> 16 & 0xFFFF).to_bytes(2, "little"), key & 0xFFFF)
    out = bytearray(data)
    for i in range(len(out)):
        c = crc16(MAGIC[i % 16:i % 16 + 1], c)
        out[i] ^= c & 0xFF
    return bytes(out)


# ---- Offline: packages, images and the write plan (no device; covered by tests/).
def package_flash(raw):
    """(identity, flash.bin) of an M-VAVE .fwsc package: the boot area and firmware, from 0x0."""
    img, ident = bytearray(), ""
    for i in range(20):     # 20 blocks of 47 bytes + 1 marker byte spelling the identity
        b = raw[i * 48:(i + 1) * 48]
        img += b[:47]
        if len(b) == 48 and b[47] != 0x7D:
            ident += chr((b[47] - i - 1) & 0xFF)
    img += raw[960:]

    def jl_enc(buf):        # UFW header cipher, key 0xFFFF
        out, k = bytearray(buf), 0xFFFF
        for i in range(len(out)):
            out[i] ^= k & 0xFF
            k = ((k << 1) ^ (0x1021 if k & 0x8000 else 0)) & 0xFFFF
        return bytes(out)
    h = jl_enc(img[:0x40])
    if len(img) < 0x40 or crc16(h[2:0x40]) != int.from_bytes(h[:2], "little"):
        raise ValueError("not an FM-1 .fwsc package")
    for i in range(int.from_bytes(h[8:10], "little")):
        e = jl_enc(img[0x40 + i * 0x50:0x90 + i * 0x50])
        if int.from_bytes(e[:2], "little") == 0:    # type 0: flash.bin
            off, n = int.from_bytes(e[8:12], "little"), int.from_bytes(e[12:16], "little")
            return ident, bytes(img[off:off + n])
    raise ValueError("no flash.bin in the package")


def recognise(ident, fl):
    """(name, tested, note) of an official package, or None."""
    known = FIRMWARE.get(ident)
    if known and len(fl) == known[1] and hashlib.sha256(fl[BOOT_END:]).hexdigest() == known[2]:
        return known[0], known[3], known[4]
    return None


def build_image(current, fl, keep_boot=False):
    """A 1 MiB image: the package's flash.bin over the backup, the rest (settings, factory) from the backup."""
    if len(current) != FLASH or not BOOT_END < len(fl) <= FACTORY:
        raise ValueError("unexpected backup or package size")
    lo = BOOT_END if keep_boot else 0
    return current[:lo] + fl[lo:] + current[len(fl):]


def plan_sectors(current, image):
    """The sectors to write, firmware first and the boot area last; never the factory sector."""
    plan = [s for s in range(0, FACTORY, SECTOR) if current[s:s + SECTOR] != image[s:s + SECTOR]]
    return [s for s in plan if s >= BOOT_END] + [s for s in plan if s < BOOT_END]


def same_unit(current, image):
    """An image keeps the unit's own factory sector: one with another unit's is refused."""
    return current[FACTORY:] == image[FACTORY:]


def cdb(op, args=b""):
    c = op.to_bytes(2, "big") + bytes(args)
    return c + b"\xff" * (16 - len(c))


def addr_len_crc(addr, data):
    return addr.to_bytes(4, "big") + len(data).to_bytes(2, "big") + b"\x00" + crc16(data).to_bytes(2, "little")


# ---- The device.
LIBUSB = ("/opt/homebrew/lib/libusb-1.0.dylib",      # Homebrew, Apple silicon
          "/usr/local/lib/libusb-1.0.dylib",         # Homebrew, Intel
          "/opt/local/lib/libusb-1.0.dylib")         # MacPorts


def usb_module():
    """pyusb, from the tool's own .venv (a plain `sudo python3 …` has no `usb`)."""
    try:
        import usb.core
        import usb.util
        import usb.backend.libusb1
    except ImportError:
        sys.exit("pyusb is missing: run the command with .venv/bin/python, after sh setup.sh (step 1).")
    return usb


def backend():
    libusb1 = usb_module().backend.libusb1
    libs = [p for p in LIBUSB if Path(p).exists()]
    be = libusb1.get_backend(find_library=(lambda name: libs[0]) if libs else None)
    if be is None:
        sys.exit("libusb was not found (it talks to the FM-1 over USB). Run sh setup.sh, or: brew install libusb")
    return be


def give_to_user(path):
    """A file written under sudo belongs to the user who ran the command, not to root."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid:
        try:
            os.chown(path, int(uid), int(gid))
        except OSError:
            pass


class Fm1:
    def __init__(self, wait=0):
        usb = self.usb = usb_module()
        be = backend()
        deadline = time.monotonic() + wait
        while (dev := usb.core.find(idVendor=VID, idProduct=PID, backend=be)) is None and time.monotonic() < deadline:
            time.sleep(0.5)
        self.dev = dev
        if self.dev is None:
            sys.exit("No FM-1 in download mode (USB 4C4A:8057). See step 3 of the guide.")
        intf = next(i for i in self.dev.get_active_configuration() if i.bInterfaceClass == 8)
        self.iface = intf.bInterfaceNumber
        self.ep_in = next(e.bEndpointAddress for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.ep_out = next(e.bEndpointAddress for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        try:
            usb.util.claim_interface(self.dev, self.iface)
        except usb.core.USBError:
            # macOS's disk driver holds it: root can take the device over (as M-Flasher does)
            try:
                self.dev.detach_kernel_driver(self.iface)
                for _ in range(10):
                    time.sleep(0.1)
                    try:
                        usb.util.claim_interface(self.dev, self.iface)
                        break
                    except usb.core.USBError:
                        pass
                else:
                    raise usb.core.USBError("still held")
            except usb.core.USBError:
                sys.exit("macOS did not release the FM-1. Run the command with sudo from Terminal, and allow "
                         "access to removable volumes if macOS asks.")
        self.tag = 0

    def execute(self, c, out=None, n_in=0):
        """One USB mass-storage (bulk-only) transaction; returns the IN data."""
        self.tag += 1
        n = len(out) if out else n_in
        cbw = (0x43425355).to_bytes(4, "little") + self.tag.to_bytes(4, "little") + n.to_bytes(4, "little")
        cbw += bytes([0x80 if n_in else 0, 0, len(c)]) + c
        self.dev.write(self.ep_out, cbw.ljust(31, b"\0"), TIMEOUT)
        data = b""
        try:
            if out:
                self.dev.write(self.ep_out, out, TIMEOUT)
            elif n_in:
                data = bytes(self.dev.read(self.ep_in, n_in, TIMEOUT))
        except self.usb.core.USBError as e:
            if e.errno != 32:   # anything but a stall
                raise
            self.dev.clear_halt(self.ep_out if out else self.ep_in)
        csw = bytes(self.dev.read(self.ep_in, 13, TIMEOUT))
        if len(csw) != 13 or csw[:4] != b"USBS" or int.from_bytes(csw[4:8], "little") != self.tag:
            raise IOError("invalid status block")
        if csw[12]:
            raise IOError("command %02X%02X failed (status %d)" % (c[0], c[1], csw[12]))
        return data

    def call(self, op, args=b""):
        r = self.execute(cdb(op, args), n_in=16)
        if len(r) != 16 or int.from_bytes(r[:2], "big") != op:
            raise IOError("command %04X: bad answer %s" % (op, r.hex()))
        return r

    def inquiry(self):
        r = self.execute(b"\x12\x00\x00\x00\x24\x00", n_in=36)
        return r[8:16].decode().strip(), r[16:32].decode().strip()

    def start_loader(self):
        addr, name, sha = LOADER
        path = HERE / "loader" / name
        if not path.is_file():
            sys.exit("loader/%s is missing. Run sh setup.sh first (step 1 of the guide)." % name)
        image = path.read_bytes()
        if hashlib.sha256(image).hexdigest() != sha:
            sys.exit("loader/%s is not the expected file. Run sh setup.sh again." % name)
        for off in range(0, len(image), 512):       # (already ciphered for this ROM)
            block = image[off:off + 512]
            self.execute(cdb(0xFB06, addr_len_crc(addr + off, block)), out=block)
        self.call(0xFB08, addr.to_bytes(4, "big") + (1).to_bytes(2, "big"))
        time.sleep(0.1)
        self.chunk = int.from_bytes(self.call(0xFC14)[2:6], "big")
        if not 256 <= self.chunk <= 16384:
            self.chunk = 512
        return addr

    def info(self):
        r = self.call(0xFC09, (0x00AC6900).to_bytes(4, "big"))
        key = int.from_bytes(crc_cipher(bytes([r[7], r[6]])), "little")
        r = self.call(0xFC0A)
        return key, r[2], int.from_bytes(r[4:8], "little")

    def read(self, addr, n, label=None):
        out = bytearray()
        while len(out) < n:
            k = min(self.chunk, n - len(out))
            d = self.execute(cdb(0xFD05, (addr + len(out)).to_bytes(4, "big") + k.to_bytes(2, "big")), n_in=k)
            if len(d) != k:
                raise IOError("read 0x%05X: %d of %d bytes" % (addr + len(out), len(d), k))
            out += d
            if label:
                print("\r%-11s %3d%%" % (label, 100 * len(out) // n), end="", flush=True)
        if label:
            print()
        return bytes(out)

    def write_sector(self, addr, data):
        assert addr % SECTOR == 0 and len(data) == SECTOR and addr + SECTOR <= FACTORY
        self.call(0xFB01, addr.to_bytes(4, "big"))                  # erase the 4 KiB sector
        step = min(self.chunk, SECTOR)
        for off in range(0, SECTOR, step):
            part = data[off:off + step]
            if any(b != 0xFF for b in part):
                self.execute(cdb(0xFB04, addr_len_crc(addr + off, part)), out=part)
        return self.read(addr, SECTOR) == data

    def reconnect(self):
        """After the FM-1 dropped off USB: wait for it, take it again, restart the loader."""
        self.usb.util.dispose_resources(self.dev)
        print("Waiting     for the FM-1 to come back on USB (up to 30 s)")
        try:
            self.__init__(wait=30)
            self.start_loader()
        except (SystemExit, self.usb.core.USBError, IOError):
            sys.exit("The FM-1 did not come back on USB. Leave it switched on and connected, put it in "
                     "download mode again, then run install (or backup and restore) again.")

    def write_sector_safe(self, addr, data):
        """write_sector with retries (an erase and program can safely be repeated)."""
        for attempt in range(4):
            try:
                if self.write_sector(addr, data):
                    return True
                print("\n            0x%05X did not verify, writing again" % addr)
            except (self.usb.core.USBError, IOError) as e:
                print("\n            0x%05X attempt %d: %s" % (addr, attempt + 1, e))
                time.sleep(0.25 * (attempt + 1))
                if getattr(e, "errno", None) == 19:     # gone from USB
                    self.reconnect()
                else:
                    try:
                        self.dev.clear_halt(self.ep_in)
                        self.dev.clear_halt(self.ep_out)
                    except self.usb.core.USBError:
                        pass
        return False


def enter_download_mode():
    """Ask a running firmware to restart into download mode (dlmode.swift, as the desktop user)."""
    user = os.environ.get("SUDO_USER")
    cmd = ["swift", str(HERE / "dlmode.swift")]
    try:    # without Apple's command line tools, /usr/bin/swift only offers to install them
        if subprocess.run(["xcode-select", "-p"], capture_output=True).returncode:
            return False
        r = subprocess.run((["sudo", "-u", user] if user else []) + cmd, capture_output=True, text=True, timeout=60)
        if r.returncode and r.stderr.strip() and not enter_download_mode.told:
            enter_download_mode.told = True
            print("Note        the download-mode request could not be sent: %s" % r.stderr.strip().splitlines()[-1])
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


enter_download_mode.told = False


def wait_download_mode(timeout=60):
    """Wait until the FM-1 is in download mode and stays there for 1 s. While a firmware runs, ask it to switch."""
    usb = usb_module()
    be, deadline, asked, seen, told = backend(), time.monotonic() + timeout, 0.0, None, False
    while time.monotonic() < deadline:
        if usb.core.find(idVendor=VID, idProduct=PID, backend=be) is not None:
            seen = seen or time.monotonic()
            if time.monotonic() - seen >= 1:
                return
        else:
            seen = None
            if time.monotonic() - asked > 10:           # (at most every 10 s: it may be starting up)
                asked = time.monotonic()
                if enter_download_mode():
                    print("Sent        download-mode request; waiting")
                elif not told:
                    told = True
                    print("Waiting     for the FM-1 in download mode (up to %d s; see step 3 of the guide)" % timeout)
        time.sleep(0.25)
    sys.exit("No FM-1 in download mode (USB 4C4A:8057) after %d s. See step 3 of the guide." % timeout)


def connect():
    wait_download_mode()
    f = Fm1(wait=5)
    vendor, product = f.inquiry()
    if vendor != "WL82" or product != "UBOOT1.00":
        sys.exit("Unexpected device %s %s: stopping." % (vendor, product))
    addr = f.start_loader()
    key, devtype, jedec = f.info()
    chip = CHIPS.get(jedec)
    print("Device      %s %s" % (vendor, product))
    print("Loader      JieLi wl82 at 0x%08X" % addr)
    print("Chip key    0x%04X   flash 0x%06X (%s)" % (key, jedec, "%s, %s" % chip if chip else "unknown chip, not tested"))
    if key != CHIP_KEY or jedec & 0xFF != 0x14:
        sys.exit("Unexpected chip key or flash size: this is not a chip the tool knows. Stopping, nothing written.")
    return f, jedec


def take_backup(f):
    """The whole flash, read twice and compared, saved as backups/fm1-DATE.bin: (data, path)."""
    a = f.read(0, FLASH, "Reading 1/2")
    b = f.read(0, FLASH, "Reading 2/2")
    if a != b:
        sys.exit("The two reads differ: flash reads are not reliable. Stopping, nothing saved.")
    path = HERE / "backups" / ("fm1-%s.bin" % time.strftime("%Y%m%d-%H%M%S"))
    if not path.parent.is_dir():
        path.parent.mkdir()
        give_to_user(path.parent)
    path.write_bytes(a)
    give_to_user(path)
    print("Backup      %s\n            sha256 %s" % (path.relative_to(HERE), hashlib.sha256(a).hexdigest()))
    return a, path


def write_plan(f, image, current, plan):
    """Write the planned sectors (firmware first, the boot area last) and verify the whole flash.
    The flash must still equal `current`; `plan` comes from plan_sectors(current, image)."""
    boot = [s for s in plan if s < BOOT_END]
    for i, s in enumerate(plan):
        if boot and s == boot[0]:
            # The boot area is the only write that can cost USB recovery: write it only after
            # everything else reads back exactly, and then without a pause.
            print()
            if f.read(BOOT_END, FACTORY - BOOT_END, "Checking firmware") != image[BOOT_END:FACTORY]:
                sys.exit("Firmware readback differs: boot area NOT written, so download mode still works. "
                         "Take a new backup, then run restore again.")
            print("Writing     boot area (%d sectors)" % len(boot))
        ok = f.write_sector_safe(s, image[s:s + SECTOR])
        print("\rWrote       0x%05X (%d/%d)" % (s, i + 1, len(plan)), end="" if ok else "\n", flush=True)
        if not ok:
            sys.exit("\n0x%05X failed after retries. Do NOT power off: run restore again with a new backup." % s)
    print()
    final = f.read(0, FLASH, "Verifying")
    if final[:FACTORY] != image[:FACTORY] or final[FACTORY:] != current[FACTORY:]:
        sys.exit("The final readback does not match. Do NOT power off: run restore again.")
    print("Done: flash matches the image (factory sector unchanged).")
    print("Unplug USB, switch the FM-1 off, wait 5 s, switch it on.")


def cmd_backup():
    f, _ = connect()
    _, path = take_backup(f)
    print("\nKeep a copy of it somewhere safe. Next, the image (step by step in the guide):\n  .venv/bin/python fm1_recover.py image FM-1.fwsc --current %s -o recovery.bin" % shlex.quote(str(path.relative_to(HERE))))


def check_package(path, allow_untested):
    """The official package at `path`: (identity, flash.bin, (name, tested, note)); stops if unknown or untested."""
    try:
        ident, fl = package_flash(Path(path).read_bytes())
    except (OSError, ValueError) as e:
        sys.exit("Stopping: %s" % e)
    known = recognise(ident, fl)
    print("Package     %s, flash.bin 0x%X bytes: %s" % (ident, len(fl), "official %s (%s)" % (
        known[0], "tested" if known[1] else "NOT yet tested") if known else "NOT a known official package"))
    if not known:
        sys.exit("Stopping: only M-VAVE's official packages are supported (docs/firmware-and-chips.md).")
    if not known[1]:
        print("Note        %s: %s." % (known[0], known[2]))
        if not allow_untested:
            sys.exit("Stopping: %s has not been confirmed with this tool yet. Use a tested version, or add "
                     "--allow-untested to go ahead at your own risk." % known[0])
    return ident, fl, known


def check_chip(jedec, allow_untested):
    if jedec not in CHIPS and not allow_untested:
        sys.exit("Stopping, nothing written: this flash chip has not been confirmed with this tool yet. "
                 "Add --allow-untested to go ahead at your own risk.")


def cmd_install(a):
    """backup, image and restore in one session: one password, one typed word. The word is asked
    first, because download mode times out while you read; then one connection takes the verified
    backup, builds the image from it (settings and factory sector kept) and writes what differs."""
    ident, fl, known = check_package(a.image, a.allow_untested)
    print("Plan        back up the whole flash, then write M-VAVE's boot area and firmware (0x0-0x%X)" % (len(fl) - 1))
    print("            where they differ; your settings area and the factory sector are kept.")
    print("Image       saved next to the backup, for a retry with restore if one is ever needed.")
    if a.check:
        print("Check       nothing is written: the plan is shown after the backup.")
    elif input("Type BOOT to back up and install %s: " % known[0]).strip() != "BOOT":
        sys.exit("Cancelled, nothing read or written.")
    f, jedec = connect()
    if not a.check:
        check_chip(jedec, a.allow_untested)
    current, path = take_backup(f)
    image = build_image(current, fl)
    out = path.with_name(path.stem + "-install-%s.bin" % known[0])
    out.write_bytes(image)
    give_to_user(out)
    plan = plan_sectors(current, image)
    boot = [s for s in plan if s < BOOT_END]
    print("Image       %s" % out.relative_to(HERE))
    print("Differs     %d sector(s)%s%s" % (len(plan), ", firmware 0x%05X-0x%05X" % (plan[0], max(s for s in plan if s >= BOOT_END) + SECTOR - 1)
                                           if any(s >= BOOT_END for s in plan) else "", ", and the boot area" if boot else ""))
    if not plan:
        print("Nothing to write: the flash already matches %s." % known[0])
        return
    if a.check:
        print("Check done: nothing written. To install, run the same command without --check, or:\n"
              "  sudo caffeinate -i .venv/bin/python fm1_recover.py restore %s --current %s%s%s"
              % (shlex.quote(str(out.relative_to(HERE))), shlex.quote(str(path.relative_to(HERE))),
                 " --allow-boot" if boot else "", " --allow-untested" if a.allow_untested else ""))
        return
    write_plan(f, image, current, plan)


def cmd_image(a):
    ident, fl, known = check_package(a.image, a.allow_untested)
    try:
        img = build_image(Path(a.current).read_bytes(), fl, a.keep_boot)
    except (OSError, ValueError) as e:
        sys.exit("Stopping: %s" % e)
    try:
        Path(a.out).write_bytes(img)
    except OSError as e:
        sys.exit("Stopping: %s" % e)
    print("Image       %s: package 0x%X-0x%X, the rest from the backup" % (a.out, BOOT_END if a.keep_boot else 0, len(fl) - 1))
    print("\nNext, the write:\n  sudo caffeinate -i .venv/bin/python fm1_recover.py restore %s --current %s --allow-boot%s"
          % (shlex.quote(a.out), shlex.quote(a.current), " --allow-untested" if not known[1] else ""))


def cmd_restore(a):
    """Plan and confirm against a backup of the FM-1 as it is now, then connect, check the flash still
    equals that backup, and write at once. Firmware first, boot area last: until the boot sectors, the
    installed bootloader stays intact, so download mode keeps working if anything goes wrong."""
    try:
        image, current = Path(a.image).read_bytes(), Path(a.current).read_bytes()
    except OSError as e:
        sys.exit("Stopping: %s" % e)
    if len(image) != FLASH or len(current) != FLASH:
        sys.exit("The image and the backup must both be exactly 1 MiB.")
    if not same_unit(current, image):
        sys.exit("Stopping: the image's factory sector differs from your backup's, so it looks like it comes "
                 "from another FM-1. Build the image from your own backup.")
    plan = plan_sectors(current, image)
    boot = [s for s in plan if s < BOOT_END]
    print("Differs     %d sector(s): %s" % (len(plan), " ".join("%05X" % s for s in plan) or "none"))
    if not plan:
        print("Nothing to write: the flash already matches the image.")
        return
    if boot and not a.allow_boot:
        sys.exit("The boot area (0x0000-0x3FFF) differs: add --allow-boot to write it.")
    word = "BOOT" if boot else "WRITE"
    if input("Type %s to erase and write these sectors: " % word).strip() != word:
        sys.exit("Cancelled, nothing written.")
    f, jedec = connect()
    check_chip(jedec, a.allow_untested)
    if f.read(0, FLASH, "Checking") != current:
        sys.exit("The flash no longer equals %s: nothing written. Take a new backup first." % a.current)
    write_plan(f, image, current, plan)


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("install", "backup", "image", "restore", "probe"))
    ap.add_argument("image", nargs="?", help="install, image: the .fwsc package; restore: the 1 MiB image")
    ap.add_argument("--check", action="store_true", help="install: back up and show the plan, write nothing")
    ap.add_argument("--current", help="a backup of the FM-1 as it is now (made by backup)")
    ap.add_argument("-o", "--out", help="image: where to save the 1 MiB image")
    ap.add_argument("--keep-boot", action="store_true", help="image: keep the boot area from the backup")
    ap.add_argument("--allow-boot", action="store_true", help="restore: allow writing the boot area 0x0000-0x3FFF")
    ap.add_argument("--allow-untested", action="store_true", help="go ahead with firmware or a flash chip not yet confirmed")
    ap.add_argument("--jieli", action="store_true", help=argparse.SUPPRESS)    # (the default; kept for old commands)
    ap.add_argument("--version", action="version", version="fm1_recover " + __version__)
    return ap


def main():
    a = build_parser().parse_args()
    try:
        run(a)
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nStopped. If a write was in progress, leave the FM-1 on and connected and run the command again.")
    except IOError as e:       # (pyusb's USBError is an IOError) a USB drop or timeout outside the retried writes
        sys.exit("\nUSB error: %s\nLeave the FM-1 switched on and connected, put it in download mode again (step 3) "
                 "and run the command again; install takes a new backup by itself." % e)


def run(a):
    if a.command == "image":
        if not (a.image and a.current and a.out):
            sys.exit("image needs: FM-1.fwsc --current BACKUP.bin -o recovery.bin")
        return cmd_image(a)
    if os.geteuid() != 0:
        sys.exit("Run this with sudo (it needs to take the FM-1 over from macOS).")
    if a.command == "install":
        if not a.image:
            sys.exit("install needs: FM-1.fwsc")
        return cmd_install(a)
    if a.command == "restore":
        if not (a.image and a.current):
            sys.exit("restore needs: IMAGE.bin --current BACKUP.bin")
        return cmd_restore(a)
    if a.command == "backup":
        return cmd_backup()
    connect()       # probe: identify the chip, read nothing


if __name__ == "__main__":
    main()
