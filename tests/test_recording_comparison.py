"""Verify the overlap-dependent FFT correlation against direct computation."""
import unittest
import numpy as np
from run_recording_comparison import lag_correlations
from run_raw_diagnostic import correlation


class RecordingComparisonTests(unittest.TestCase):
    def test_fft_matches_direct_per_polarity_overlap_centring(self):
        rng = np.random.default_rng(17)
        counts = rng.poisson(np.linspace(1, 100, 137)[:, None] * np.array([1, 3]), size=(137, 2))
        lags = np.array([1, 3, 19, 60, 110])
        np.testing.assert_allclose(lag_correlations(counts, lags),
                                   [correlation(counts, lag) for lag in lags], atol=1e-11)

    def test_constant_imbalance_cannot_supply_recurrence(self):
        counts = np.tile([1, 100], (137, 1))
        self.assertTrue(np.isnan(lag_correlations(counts, [1, 5, 60])).all())

    def test_invalid_lags_rejected(self):
        with self.assertRaises(ValueError):
            lag_correlations(np.ones((10, 2)), [0])


if __name__ == "__main__":
    unittest.main()
