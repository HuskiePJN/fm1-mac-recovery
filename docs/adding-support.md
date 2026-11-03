# Adding support

New FM-1 firmware versions and flash chips are added in one place: the tables near the top of `fm1_recover.py`. Keep the bar the same for every entry: recognised by exact hashes, and marked tested only after a real recovery.

## A new official firmware version

1. Get the `.fwsc` from M-VAVE. Never commit it.
2. Read its identity and `flash.bin`, and hash the part after the boot area:

   ```sh
   .venv/bin/python -c "import hashlib,fm1_recover as r; i,f=r.package_flash(open('FM-1.fwsc','rb').read()); print(i, hex(len(f)), hashlib.sha256(f[0x4000:]).hexdigest(), hashlib.sha256(f[:0x4000]).hexdigest()[:12])"
   ```

3. Add a line to `FIRMWARE` with the identity, a short name, the size, the hash, `False` (not yet tested) and a note. Say in the note whether its boot area differs from V15's.
4. Add it to [firmware-and-chips.md](firmware-and-chips.md) and to the [changelog](../CHANGELOG.md).
5. Run the tests, also against the real files: `FM1_PACKAGES=/path/to/folder python3 -m unittest discover tests`.
6. Change it to `True` only after an FM-1 was recovered with it and started, and record that recovery in the tested table.

Check before adding:

- `flash.bin` must end before `0xFF000`. The tests reject anything that reaches the factory sector.
- If the firmware grows past the old one, note which settings area it now covers. The image keeps everything after `flash.bin` from the unit's backup.

## A new flash chip

1. Run `sudo .venv/bin/python fm1_recover.py probe` and note the `flash 0x......` value. `probe` reads nothing from the flash.
2. Make sure it is a 1 MiB chip (the ID ends in `14`) and find its datasheet.
3. Add it to `CHIPS` as `"expected"` until a recovery on it is confirmed, then `"tested"`.
4. Update [firmware-and-chips.md](firmware-and-chips.md) and the changelog.

## Releases

- Bump `__version__` in `fm1_recover.py`, add a changelog entry, and tag `vX.Y.Z`.
- The offline tests run on every push (`.github/workflows/tests.yml`). They need no FM-1.
- A change to how the tool reads or writes needs a real check on an FM-1 before release: a backup, then a one-sector write and restore on an empty sector outside the firmware, the method used for 1.0.0 (see [firmware-and-chips.md](firmware-and-chips.md)).
