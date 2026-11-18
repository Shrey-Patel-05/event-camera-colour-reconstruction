"""Golden event fixture: polarity, exact boundaries, time origin and maps."""
import tempfile
from pathlib import Path
import unittest

import numpy as np

from run_raw_diagnostic import load_psee, raw_scan, correlation, ROOT


class RawDiagnosticTests(unittest.TestCase):
    def test_psee_histogram_and_maps_use_half_open_file_relative_windows(self):
        toolbox = ROOT.parent / "prophesee-automotive-dataset-toolbox"
        if not toolbox.is_dir():
            self.skipTest("Prophesee toolbox not installed beside repository")
        loader_class = load_psee(toolbox)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture.dat"
            # Same timestamp, both polarities; right endpoint must be excluded.
            t = np.array([1000, 1049, 1050, 1050, 1099, 1100], dtype="<u4")
            x = np.array([0, 1, 0, 1, 1, 0], dtype="<u4")
            p = np.array([1, 0, 0, 1, 1, 0], dtype="<u4")
            records = np.empty((6, 2), dtype="<u4")
            records[:, 0] = t
            records[:, 1] = x | (p << 28)
            path.write_bytes(b"% Version 2\n% Height 1\n% Width 2\n" + bytes([12, 8]) + records.tobytes())
            counts, maps, invalid = raw_scan(loader_class(str(path)), 1000,
                                             0, 100, 50, [0, 50], 50)
            np.testing.assert_array_equal(counts, [[1, 1], [1, 2]])
            np.testing.assert_array_equal(maps[0], [[[0, 1]], [[1, 0]]])
            np.testing.assert_array_equal(maps[1], [[[1, 0]], [[0, 2]]])
            self.assertEqual(invalid, 0)

    def test_recurrence_does_not_use_constant_polarity_imbalance(self):
        self.assertIsNone(correlation(np.tile([1, 100], (20, 1)), 4))
        pattern = np.array([[0, 1], [2, 0], [0, 5], [3, 0]])
        self.assertAlmostEqual(correlation(np.tile(pattern, (10, 1)), 4), 1)


if __name__ == "__main__":
    unittest.main()
