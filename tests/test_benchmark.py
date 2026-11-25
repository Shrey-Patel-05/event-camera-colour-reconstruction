import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from run_benchmark import (
    classify, load_design, macro_mean, metrics, recording_timing, repeatability,
)
from swatch_rois import load_layout, save_layout


def response_rows():
    rows = []
    for repeat, counts in enumerate(([2, 3, 5], [4, 7, 10], [20, 1, 2]), 1):
        for colour, count in zip("RGB", counts):
            rows.append(dict(roi="ROI_1", colour=colour, repeat=repeat, roi_area_pixels=100,
                             on=count, on_density=count / 100))
    return rows


class BenchmarkTests(unittest.TestCase):
    def test_loss_direction_scale_and_display_brightness(self):
        result = metrics([0.5, 0.5, 0], [90, 90, 0], [0, 90, 90])
        self.assertEqual(result["balance_loss"], 0.5)
        self.assertEqual(result["bias_R_pp"], 50)
        self.assertEqual(result["bias_B_pp"], -50)
        self.assertEqual(result["rgb_mae"], 60)
        self.assertEqual(metrics([0, .5, .5], [0, 45, 45], [0, 90, 90])["balance_loss"], 0)

    def test_unit_of_analysis(self):
        rows = [dict(swatch="black", recording=k, loss=v)
                for k, v in (("a", 0), ("a", 0), ("b", 1))]
        rows.append(dict(swatch="red", recording="c", loss=1))
        self.assertEqual(macro_mean(rows, "loss"), 0.75)

    def test_scope_and_protocol(self):
        design = load_design()
        for suffix in ("N2", "SR", "J1_T2"):
            with self.assertRaises(ValueError):
                classify(Path(f"purple/purple_{suffix}_20261116.dat"), design)
        run, profile = classify(Path("light_blue/light_blue_CA2_T2_20261116.dat"), design)
        self.assertEqual((run["id"], profile), ("CA2", "T2"))

    def test_labels_masks_and_resolution(self):
        points = np.array([[1, 1], [5, 1], [4, 6]], dtype=np.int32)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "layout.json"
            save_layout(path, "red", "r.dat", 10, 8, {"ROI_1": points}, {"ROI_1": "red"})
            polygons, labels = load_layout(path, 10, 8)
            np.testing.assert_array_equal(polygons["ROI_1"], points)
            self.assertEqual(labels, {"ROI_1": "red"})
            with self.assertRaises(ValueError):
                load_layout(path, 8, 10)
            layout = json.loads(path.read_text())
            layout["rois"]["ROI_1"]["points"][0][0] = 10
            path.write_text(json.dumps(layout))
            with self.assertRaises(ValueError):
                load_layout(path, 10, 8)

    def test_repeatability_keeps_profiles_and_rejected_captures_separate(self):
        runs = [("CA1", "T2", 1.), ("CA2", "T2", .4), ("CA3", "T2", None),
                ("CA1", "T1", 0.), ("T2", "T2", 0.)]
        scores, inventory = [], {}
        for i, (run, profile, red) in enumerate(runs):
            name = f"red/{i}.dat"
            inventory[name] = dict(run=run)
            row = dict(recording=name, swatch="red", roi="ROI_1", profile=profile, arm="A",
                       status="rejected")
            if red is not None:
                row.update(status="ok", share_R=red, share_G=1-red, share_B=0, balance_loss=1-red)
            scores.append(row)
        by_profile = {r["profile"]: r for r in repeatability(inventory, scores)}
        t2 = by_profile["T2"]
        self.assertEqual((t2["available_takes"], t2["scored_takes"], t2["pairs"]), (3, 2, 1))
        self.assertAlmostEqual(t2["mean_pair_distance"], .6)
        self.assertAlmostEqual(t2["mean_target_loss"], .3)
        self.assertIsNone(by_profile["T1"]["mean_pair_distance"])

    def test_recording_timing_matches_arduino_profiles(self):
        design = load_design()
        for name, on, off in (("T1", 1000, 500), ("T2", 1000, 5000), ("T3", 5000, 5000),
                              ("CA1", 1000, 5000), ("CA2", 1000, 5000), ("CA3", 1000, 5000),
                              ("L2", 500, 500)):
            run = next(r for r in design["runs"] if r["id"] == name)
            profile = "T2" if name.startswith("CA") else name
            timing, basis = recording_timing(design, run, profile)
            self.assertEqual((timing.fade_duration_us, timing.dark_interval_us,
                              timing.flash_period_us, timing.response_window_us),
                             (on, off, on + off, on))
            self.assertEqual(timing.num_rgb_repeats, 3)
            self.assertEqual(timing.response_delay_us, 0)
            if name == "L2":
                self.assertIn("nominal", basis)


if __name__ == "__main__":
    unittest.main()
