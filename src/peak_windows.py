"""Build recording-specific RGB response windows from the timing diagnostic CSV."""

from __future__ import annotations

import csv
from pathlib import Path


def read_peak_windows(path: Path, width_us: int) -> list[dict]:
    """Use the measured G/B median in each cycle. Times are from the first DAT event."""
    if width_us <= 0 or width_us % 2:
        raise ValueError("Peak window width must be a positive even number of microseconds.")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"stage", "cycle", "led", "coverage", "target_on_us", "slot_end_us",
                    "slot_ON_peak_bin_after_target_on_us"}
        if required.difference(reader.fieldnames or ()):
            raise ValueError("Peak CSV must be a stage_statistics.csv from the timing diagnostic.")
        stages = list(reader)
    if not stages or len(stages) % 3:
        raise ValueError("Peak CSV must contain one or more complete RGB cycles.")

    windows = []
    half_width = width_us // 2
    previous_target = -1
    previous_end = 0
    for i in range(0, len(stages), 3):
        rgb = stages[i:i + 3]
        cycle = i // 3 + 1
        try:
            for j, (row, colour) in enumerate(zip(rgb, "RGB")):
                if (int(row["stage"]) != i + j + 1 or int(row["cycle"]) != cycle
                        or row["led"] != colour or row["coverage"] != "complete"):
                    raise ValueError("Expected consecutive, fully covered R, G and B stages.")
            targets = [int(row["target_on_us"]) for row in rgb]
            green, blue = (int(row["slot_ON_peak_bin_after_target_on_us"]) for row in rgb[1:])
            for row, target, offset in zip(rgb[1:], targets[1:], (green, blue)):
                if not 0 <= offset < int(row["slot_end_us"]) - target:
                    raise ValueError("G/B peak offset falls outside its source slot.")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid timing data in cycle {cycle}: {error}") from error

        # With two values the median is their mean, rounded to the nearest integer us.
        phase = (green + blue + 1) // 2
        for j, (target, colour) in enumerate(zip(targets, "RGB")):
            peak = target + phase
            start, end = peak - half_width, peak + half_width
            if target <= previous_target or start < previous_end:
                raise ValueError(f"Non-increasing targets or overlapping response windows at {colour}{cycle}.")
            windows.append(dict(stage=i + j + 1, cycle=cycle, led=colour, target_on_us=target,
                                green_peak_offset_us=green, blue_peak_offset_us=blue,
                                phase_us=phase, peak_us=peak, window_start_us=start, window_end_us=end))
            previous_target, previous_end = target, end
    return windows
