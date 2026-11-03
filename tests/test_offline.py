# SPDX-License-Identifier: MIT
"""Offline checks of fm1_recover.py: package parsing, image building and the write plan.

No FM-1, libusb or firmware file is needed: the packages here are synthetic. Set FM1_PACKAGES to a
folder of real .fwsc files to also check that each known official package is recognised.
    python3 -m unittest discover tests
"""
import hashlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fm1_recover as r  # noqa: E402


def jl_enc(buf):
    out, k = bytearray(buf), 0xFFFF
    for i in range(len(out)):
        out[i] ^= k & 0xFF
        k = ((k << 1) ^ (0x1021 if k & 0x8000 else 0)) & 0xFFFF
    return bytes(out)


def make_package(ident, flash_bin):
    """A minimal .fwsc in M-VAVE's layout: a UFW header with one flash.bin entry, wrapped in the
    20-block identity framing."""
    off = 0x90
    header = bytearray(0x40)
    header[8:10] = (1).to_bytes(2, "little")
    entry = bytearray(0x50)
    entry[8:12] = off.to_bytes(4, "little")
    entry[12:16] = len(flash_bin).to_bytes(4, "little")
    header[:2] = r.crc16(bytes(header[2:])).to_bytes(2, "little")
    img = jl_enc(bytes(header)) + jl_enc(bytes(entry)) + flash_bin
    raw = bytearray()
    for i in range(20):
        mark = (ord(ident[i]) + i + 1) & 0xFF if i < len(ident) else 0x7D
        raw += img[i * 47:(i + 1) * 47] + bytes([mark])
    return bytes(raw + img[940:])


def flash(fill, factory=b"F"):
    """A 1 MiB backup: every sector filled with one byte, the factory sector with another."""
    return bytes([fill]) * r.FACTORY + factory * (r.FLASH - r.FACTORY)


class Package(unittest.TestCase):
    def test_round_trip(self):
        fl = bytes(range(256)) * 0x930
        ident, out = r.package_flash(make_package("FM-1_015", fl))
        self.assertEqual((ident, out), ("FM-1_015", fl))

    def test_not_a_package(self):
        with self.assertRaises(ValueError):
            r.package_flash(b"\0" * 4096)

    def test_unknown_package_not_recognised(self):
        fl = b"\xAA" * 0x93000
        self.assertIsNone(r.recognise("FM-1_015", fl))       # right identity, wrong contents
        self.assertIsNone(r.recognise("FM-1_900", fl))       # not an official identity

    def test_recognised_by_hash(self):
        fl = b"\x11" * 0x93000
        saved = dict(r.FIRMWARE)
        try:
            r.FIRMWARE["TEST_1"] = ("T1", len(fl), hashlib.sha256(fl[r.BOOT_END:]).hexdigest(), False, "a test")
            self.assertEqual(r.recognise("TEST_1", fl), ("T1", False, "a test"))
            self.assertIsNone(r.recognise("TEST_1", fl[:-1]))   # a different size
        finally:
            r.FIRMWARE.clear()
            r.FIRMWARE.update(saved)

    @unittest.skipUnless(os.environ.get("FM1_PACKAGES"), "set FM1_PACKAGES to a folder of real .fwsc files")
    def test_real_packages(self):
        seen = 0
        for p in sorted(Path(os.environ["FM1_PACKAGES"]).glob("*.fwsc")):
            ident, fl = r.package_flash(p.read_bytes())
            if ident in r.FIRMWARE:
                self.assertIsNotNone(r.recognise(ident, fl), p.name)
                seen += 1
        self.assertGreater(seen, 0)


class Image(unittest.TestCase):
    def test_package_over_backup(self):
        current, fl = flash(0x33), b"\x77" * 0x93000
        img = r.build_image(current, fl)
        self.assertEqual(len(img), r.FLASH)
        self.assertEqual(img[:0x93000], fl)                        # boot area and firmware: the package
        self.assertEqual(img[0x93000:], current[0x93000:])         # settings and factory: the backup

    def test_keep_boot(self):
        current, fl = flash(0x33), b"\x77" * 0x93000
        img = r.build_image(current, fl, keep_boot=True)
        self.assertEqual(img[:r.BOOT_END], current[:r.BOOT_END])
        self.assertEqual(img[r.BOOT_END:0x93000], fl[r.BOOT_END:])

    def test_sizes_refused(self):
        with self.assertRaises(ValueError):
            r.build_image(flash(0)[:-1], b"\0" * 0x93000)          # not a 1 MiB backup
        with self.assertRaises(ValueError):
            r.build_image(flash(0), b"\0" * (r.FACTORY + 1))        # a package reaching the factory sector


class Plan(unittest.TestCase):
    def test_boot_last_factory_never(self):
        current, image = flash(0x00), flash(0x01, factory=b"G")
        plan = r.plan_sectors(current, image)
        self.assertEqual(len(plan), r.FACTORY // r.SECTOR)
        self.assertNotIn(r.FACTORY, plan)
        self.assertEqual(plan[-4:], [0x0000, 0x1000, 0x2000, 0x3000])
        self.assertTrue(all(s >= r.BOOT_END for s in plan[:-4]))

    def test_only_changed_sectors(self):
        current = bytearray(flash(0x00))
        image = bytearray(current)
        image[0x50000] = 1
        image[0x1234] = 1
        self.assertEqual(r.plan_sectors(bytes(current), bytes(image)), [0x50000, 0x1000])
        self.assertEqual(r.plan_sectors(bytes(current), bytes(current)), [])

    def test_other_unit_refused(self):
        self.assertTrue(r.same_unit(flash(0), flash(1)))
        self.assertFalse(r.same_unit(flash(0), flash(0, factory=b"X")))


class Known(unittest.TestCase):
    def test_tables(self):
        for ident, (name, end, sha, tested, note) in r.FIRMWARE.items():
            self.assertTrue(r.BOOT_END < end <= r.FACTORY and end % r.SECTOR == 0, ident)
            self.assertEqual(len(sha), 64, ident)
        for jedec, (name, status) in r.CHIPS.items():
            self.assertEqual(jedec & 0xFF, 0x14, name)                # 1 MiB
            self.assertIn(status, ("tested", "expected"), name)


if __name__ == "__main__":
    unittest.main()
