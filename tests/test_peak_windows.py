import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.peak_windows import read_peak_windows


class PeakWindowTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "stage_statistics.csv"
        self.stages = [
            dict(stage=i + 1, cycle=i // 3 + 1, led=led, coverage="complete",
                 target_on_us=10000 + 6000 * i, slot_end_us=16000 + 6000 * i,
                 slot_ON_peak_bin_after_target_on_us=offset)
            for i, (led, offset) in enumerate(zip("RGBRGB", ["", 1600, 1300, 0, 5900, 5800]))
        ]

    def write_stages(self):
        with self.path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(self.stages[0]))
            writer.writeheader()
            writer.writerows(self.stages)

    def test_shared_phase_ignores_red_and_preserves_late_windows(self):
        self.write_stages()
        windows = read_peak_windows(self.path, width_us=500)
        self.assertEqual([row["phase_us"] for row in windows], [1450] * 3 + [5850] * 3)
        self.assertEqual([row["window_start_us"] for row in windows[:3]], [11200, 17200, 23200])
        self.assertEqual(windows[-1]["window_end_us"], self.stages[-1]["slot_end_us"] + 100)
        self.assertTrue(all(row["window_end_us"] - row["window_start_us"] == 500
                            for row in windows))

    def test_missing_blue_peak_stops_the_run(self):
        self.stages[-1]["slot_ON_peak_bin_after_target_on_us"] = ""
        self.write_stages()
        with self.assertRaisesRegex(ValueError, "Invalid timing data in cycle 2"):
            read_peak_windows(self.path, width_us=500)

    def test_overlapping_windows_stop_the_run(self):
        self.write_stages()
        with self.assertRaisesRegex(ValueError, "overlapping"):
            read_peak_windows(self.path, width_us=6200)


if __name__ == "__main__":
    unittest.main()
