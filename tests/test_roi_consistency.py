"""Golden DAT check for the new diagnostic against Yan's existing counter."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from run_roi_consistency import (scan_activity, compare_saved, read_dat_header,
    count_roi_flash_responses_chunked, TimingConfig)


class ROIConsistencyTests(unittest.TestCase):
    def test_raw_histograms_match_counter_with_different_seek_and_time_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "small.dat"
            # First event establishes the origin. Same-timestamp polarities,
            # a dark-interval boundary and one invalid pixel exercise membership.
            relative = [0, 100, 100, 149, 199, 200, 250, 275, 1300, 1399, 1400, 1401]
            x = np.array([0, 0, 0, 1, 0, 0, 0, 4, 0, 1, 0, 0], dtype="<u4")
            y = np.array([0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0], dtype="<u4")
            p = np.array([1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1], dtype="<u4")
            words = np.empty((len(relative), 2), dtype="<u4")
            words[:, 0] = np.array(relative) + 5000
            words[:, 1] = x | (y << 14) | (p << 28)
            path.write_bytes(b"% Version 2\n% Height 300\n% Width 3\n" + bytes([12, 8]) + words.tobytes())
            header = read_dat_header(path)
            masks = {name: np.zeros((300, 3), dtype=bool) for name in ["ROI_1", "ROI_2"]}
            masks["ROI_1"][0, 0] = True
            masks["ROI_2"][:2, 1] = True
            areas = {k: int(v.sum()) for k, v in masks.items()}
            timing = TimingConfig(fade_duration_us=100, dark_interval_us=50,
                flash_period_us=150, response_window_us=100, flash_detection_bin_us=5,
                timing_edge_guard_us=10)
            onsets_relative_to_read = 80 + np.arange(9) * 150
            rows = count_roi_flash_responses_chunked(path, header.data_start,
                5020, 20, onsets_relative_to_read, masks, areas, 3, 300, timing, chunk_events=3)
            names, hist, images, invalid = scan_activity(path, header, masks,
                                                         50, 1450, 50, [(100, 200)])
            self.assertEqual(invalid, 1)
            for r in rows:
                lo, hi = (r["window_start_us"] - 50) // 50, (r["window_end_us"] - 50) // 50
                np.testing.assert_array_equal(hist[names.index(r["roi"]), lo:hi].sum(axis=0),
                                              [r["off"], r["on"]])
            first = rows[0]
            self.assertEqual((first["on"], first["off"]), (2, 1))
            self.assertEqual((first["window_start_us"], first["window_end_us"]), (100, 200))
            self.assertEqual(rows[1]["on_density"], 0.5)
            self.assertEqual(images.sum(), 4)

    def test_reproduction_comparison_rejects_changed_density(self):
        saved = [dict(roi="ROI_1", on="10", on_density="0.5")]
        self.assertEqual(compare_saved([dict(roi="ROI_1", on=10, on_density=.5)],
                                       saved, ["roi"])["max_absolute_error"], 0)
        with self.assertRaises(ValueError):
            compare_saved([dict(roi="ROI_1", on=10, on_density=.6)], saved, ["roi"])


if __name__ == "__main__":
    unittest.main()
