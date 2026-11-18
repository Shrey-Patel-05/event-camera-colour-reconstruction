"""Input-integrity tests for the offline firmware audit."""
from pathlib import Path
import tempfile
import unittest

from audit_arduino_backup import read_ihex, verify_listing


class ArduinoAuditTests(unittest.TestCase):
    def test_ihex_checksum_eof_and_listing_crosscheck(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            hexfile = p / "small.hex"
            hexfile.write_text(":040000000C945D00FF\n:00000001FF\n")
            memory, kinds = read_ihex(hexfile)
            self.assertEqual(bytes(memory.values()), bytes.fromhex("0c 94 5d 00"))
            listing = p / "listing.txt"
            listing.write_text("  0:\t0c 94 5d 00 \tjmp\t0xba\n")
            instructions, covered = verify_listing(listing, memory)
            self.assertEqual(covered, {0, 1, 2, 3})
            self.assertEqual(instructions[0]["bytes"], "0c 94 5d 00")
            listing.write_text("  0:\t0c 94 5e 00 \tjmp\t0xbc\n")
            with self.assertRaises(ValueError):
                verify_listing(listing, memory)

    def test_bad_checksum_and_missing_eof_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.hex"
            path.write_text(":040000000C945D00FE\n:00000001FF\n")
            with self.assertRaises(ValueError):
                read_ihex(path)
            path.write_text(":040000000C945D00FF\n")
            with self.assertRaises(ValueError):
                read_ihex(path)


if __name__ == "__main__":
    unittest.main()
