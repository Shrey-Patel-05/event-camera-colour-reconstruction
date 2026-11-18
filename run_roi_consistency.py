"""Experiment 1D: audit saved polygon-ROI responses without changing the baseline.

Uses the existing mask, counting, repeatability and colour-estimation functions.
Times in exports are microseconds after the first DAT event. Output directories
must be new. See docs/experiment_1d.md for method and reproduction commands.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from dat_decoder import read_dat_header, find_file_position_at_timestamp, iter_event_chunks
from temporal_alignment import TimingConfig, build_fixed_flash_onsets
from roi_analysis import (make_roi_masks, prepare_analysis_roi_masks,
                          count_roi_flash_responses_chunked, calculate_repeatability_summary,
                          calculate_on_activity_brightness, save_effective_roi_mask_figure,
                          save_roi_response_figure, write_csv)
from colour_mapping import build_roi_colours, ColourConfig
from run_duration_experiment import (Experiment, add_derived_measurements,
                                     calculate_response_summaries)

COLOURS = ("R", "G", "B")
PALETTE = ("#bc4749", "#368548", "#356fbb")


def read_csv(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def compare_saved(actual, saved, keys):
    """Compare every saved numeric/text field, including densities and display data."""
    def identity(r):
        return tuple(str(r[k]) for k in keys)
    lookup = {identity(r): r for r in saved}
    if len(actual) != len(saved) or len(lookup) != len(saved):
        raise ValueError("Saved and reproduced table sizes differ")
    max_error = 0.0
    fields = 0
    for row in actual:
        previous = lookup[identity(row)]
        for key, old in previous.items():
            new = row[key]
            try:
                old_float, new_float = float(old), float(new)
            except (ValueError, TypeError):
                if str(new) != old:
                    raise ValueError(f"Text mismatch in {identity(row)}: {key}")
                continue
            if not np.isclose(old_float, new_float, rtol=1e-12, atol=1e-12, equal_nan=True):
                raise ValueError(f"Numeric mismatch in {identity(row)}: {key}: {new} != {old}")
            if np.isfinite(old_float) and np.isfinite(new_float):
                max_error = max(max_error, abs(old_float - new_float))
            fields += 1
    return dict(rows=len(actual), numeric_fields=fields, max_absolute_error=max_error)


def estimate(rows, experiment):
    brightness = calculate_on_activity_brightness(rows, reference_roi="ROI_1")
    _, peaks, repeats = build_roi_colours(rows, brightness, ColourConfig())
    derived = add_derived_measurements(rows, experiment, "FULL")
    summaries = [r for method in ("ON_PEAK", "ON_MEAN", "ON_MEDIAN")
                 for r in calculate_response_summaries(derived, method)]
    return peaks, repeats, summaries


def scan_activity(dat, header, masks, start, end, bin_us, snapshots):
    """Diagnostic histograms only; quantitative colour results use Yan's counter."""
    names = ["whole_sensor", *masks]
    n = (end - start + bin_us - 1) // bin_us
    hist = np.zeros((len(names), n, 2), dtype=np.int64)  # OFF, ON
    images = np.zeros((len(snapshots), 2, header.height, header.width), dtype=np.int64)
    position, _, _ = find_file_position_at_timestamp(dat, header.data_start,
                                                     header.file_first_timestamp + start)
    invalid = 0
    for ts, x, y, p in iter_event_chunks(dat, position, header.file_first_timestamp + end):
        t = ts.astype(np.int64) - header.file_first_timestamp
        valid_time = (t >= start) & (t < end)
        t, x, y, p = t[valid_time], x[valid_time], y[valid_time], p[valid_time]
        indices = (t - start) // bin_us * 2 + p
        hist[0] += np.bincount(indices, minlength=n * 2).reshape(n, 2)
        valid_xy = (x >= 0) & (x < header.width) & (y >= 0) & (y < header.height)
        invalid += int((~valid_xy).sum())
        for i, mask in enumerate(masks.values(), 1):
            inside = np.zeros(len(t), dtype=bool)
            inside[valid_xy] = mask[y[valid_xy], x[valid_xy]]
            hist[i] += np.bincount(indices[inside], minlength=n * 2).reshape(n, 2)
        for i, (left, right) in enumerate(snapshots):
            keep = valid_xy & (t >= left) & (t < right)
            flat = p[keep].astype(np.int64) * header.height * header.width + y[keep] * header.width + x[keep]
            images[i] += np.bincount(flat, minlength=2 * header.height * header.width).reshape(
                2, header.height, header.width)
    return names, hist, images, invalid


def shade(ax, rows, limits, labels=False):
    for row in rows:
        left, right = row["window_start_us"], row["window_end_us"]
        if right < limits[0] or left > limits[1]:
            continue
        colour = "tab:green" if row["timing_supported"] else "tab:red"
        ax.axvspan(left / 1e6, right / 1e6, color=colour, alpha=.10)
        ax.axvline(left / 1e6, color=colour, lw=.6)
        if labels and limits[0] <= left <= limits[1]:
            ax.text(left / 1e6, .98, row["stage"] + (" ✓" if row["timing_supported"] else " ×"),
                    transform=ax.get_xaxis_transform(), va="top", fontsize=8)


def activity_plot(path, names, hist, start, bin_us, stage_rows, limits):
    t = (start + np.arange(hist.shape[1]) * bin_us) / 1e6
    fig, axes = plt.subplots(len(names), 1, figsize=(16, 2.1 * len(names)),
                             sharex=True, constrained_layout=True)
    for i, (ax, name) in enumerate(zip(axes, names)):
        ax.step(t, hist[i, :, 1], where="post", color="#d47e14", lw=.75, label="ON")
        ax.step(t, hist[i, :, 0], where="post", color="#386ca1", lw=.75, label="OFF")
        ax.set_yscale("symlog", linthresh=5)
        ax.set_ylabel(f"{name}\nevents / {bin_us} µs")
        shade(ax, stage_rows, limits, labels=i == 0)
        ax.set_xlim(np.array(limits) / 1e6)
        ax.grid(alpha=.12)
    axes[0].legend(loc="upper right")
    axes[-1].set_xlabel("Seconds after first DAT event")
    fig.suptitle("Raw global and fixed-ROI activity; independent y scales\n"
                 "Shading: predicted response windows; green supported / red unsupported globally")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def repetition_plot(path, rows, names):
    fig, axes = plt.subplots(len(names), 3, figsize=(13, 2.5 * len(names)),
                             constrained_layout=True, squeeze=False)
    for i, name in enumerate(names):
        for j, colour in enumerate(COLOURS):
            values = [r for r in rows if r["roi"] == name and r["colour"] == colour]
            ax = axes[i, j]
            x = np.arange(len(values))
            for offset, metric, display in [(-.18, "on_density", "ON"), (.18, "off_density", "OFF")]:
                ax.bar(x + offset, [r[metric] for r in values], width=.36,
                       color="#d47e14" if display == "ON" else "#386ca1", label=display)
            ax.set_xticks(x, [r["stage"] + (" ×" if not r["timing_supported"] else "") for r in values])
            ax.set_title(f"{name}: predicted {colour}")
            ax.set_ylabel("Events / effective ROI pixel")
            ax.grid(axis="y", alpha=.15)
    axes[0, 0].legend()
    fig.suptitle("Every repetition retained; × = globally unsupported model window")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def phase_analysis(path, names, hist, start, bin_us, rows, areas):
    fig, axes = plt.subplots(len(areas), 3, figsize=(13, 2.6 * len(areas)),
                             constrained_layout=True, squeeze=False)
    summaries = []
    correlations = []
    for i, name in enumerate(areas):
        for j, colour in enumerate(COLOURS):
            profiles = []
            for row in [r for r in rows if r["roi"] == name and r["colour"] == colour]:
                left = (row["window_start_us"] - start) // bin_us
                right = (row["window_end_us"] - start) // bin_us
                values = hist[names.index(name), left:right, 1]
                offsets = (np.arange(len(values)) + .5) * bin_us
                axes[i, j].step(offsets / 1000, values / areas[name], where="mid",
                                lw=.75, label=row["stage"])
                # Use integrated 1 ms slices as a coarse location-of-response diagnostic.
                factor = 1000 // bin_us
                coarse = values[:len(values) // factor * factor].reshape(-1, factor).sum(axis=1)
                summaries.append(dict(roi=name, stage=row["stage"], ON=int(values.sum()),
                                      peak_1ms_slice_start_us=int(np.argmax(coarse) * 1000) if values.sum() else None,
                                      ON_weighted_centroid_us=float(np.dot(offsets, values) / values.sum()) if values.sum() else None))
                profiles.append(values)
            for a, b in [(0, 1), (0, 2), (1, 2)]:
                x, y = np.log1p(profiles[a]), np.log1p(profiles[b])
                corr = float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else None
                correlations.append(dict(roi=name, predicted_colour=colour,
                                         repeat_a=a + 1, repeat_b=b + 1,
                                         log_ON_profile_correlation=corr))
            axes[i, j].set_title(f"{name}: predicted {colour}")
            axes[i, j].set_xlabel("Time within predicted response window (ms)")
            axes[i, j].set_ylabel(f"ON / pixel / {bin_us} µs")
            axes[i, j].legend(fontsize=8)
    fig.suptitle("Response location within model windows; these are not measured LED onsets")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return summaries, correlations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, default=ROOT / "data/10ms_4s.dat")
    parser.add_argument("--saved-run", type=Path, default=ROOT / "new_led_full_recording_results/10ms_4s/20261022_125050_727915")
    parser.add_argument("--evidence", type=Path, default=ROOT / "diagnostics/experiment_1_10ms/evidence.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--primary-roi", default="ROI_1")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text())
    meta = json.loads((args.saved_run / "analysis_metadata.json").read_text())
    header = read_dat_header(args.dat)
    if Path(meta["data_file"]).name != args.dat.name or Path(evidence["data_file"]).resolve() != args.dat.resolve():
        raise ValueError("DAT and baseline evidence must identify the same recording")
    if (header.file_first_timestamp != evidence["first_DAT_timestamp_us"] or
            args.dat.stat().st_size != evidence["file_size_bytes"]):
        raise ValueError("DAT header/size differs from Experiment 1")
    timing = TimingConfig(**evidence["timing"])
    actual_read = int(meta["actual_read_start_us"])
    onsets = build_fixed_flash_onsets(int(meta["timing_detection"]["first_onset_after_sync_us"]), timing)
    if (onsets + actual_read).tolist() != evidence["rerun_onsets_after_file_first_us"]:
        raise ValueError("Saved phase and verified detector rerun disagree")
    checks = read_csv(args.saved_run / "automatic_timing_check.csv")
    support = {c["stage"]: c["supported"].lower() == "true" for c in checks}
    polygons = {k: np.array(v, dtype=np.int32) for k, v in meta["polygons"].items()}
    raw, raw_areas = make_roi_masks(polygons, header.width, header.height)
    definitions = [(name, name, (255, 255, 255)) for name in polygons]
    masks, areas, regions = prepare_analysis_roi_masks(raw, definitions,
                                                      meta["roi_region_details"]["mode"])
    if areas != meta["effective_roi_areas"] or raw_areas != meta["raw_roi_areas"]:
        raise ValueError("Reconstructed mask areas differ from saved run")
    if args.primary_roi not in masks:
        raise ValueError("Primary ROI not present in saved masks")
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    reference = cv2.imread(str(args.saved_run / "roi_reference.png"), cv2.IMREAD_GRAYSCALE)
    if reference is None or reference.shape != (header.height, header.width):
        raise ValueError("Missing or incorrectly sized saved ROI reference")
    save_effective_roi_mask_figure(reference, polygons, masks, out / "roi_effective_masks.png")
    saved_mask = cv2.imread(str(args.saved_run / "roi_effective_masks.png"))
    recreated = cv2.imread(str(out / "roi_effective_masks.png"))
    if saved_mask is None or saved_mask.shape != recreated.shape:
        raise ValueError("Missing or incorrectly sized saved effective-mask figure")
    different = np.any(saved_mask != recreated, axis=2)
    annotation = np.zeros(different.shape, dtype=bool)
    for polygon in polygons.values():
        x, y = polygon[0]
        annotation[max(0, y - 25):y + 10, max(0, x - 5):x + 90] = True
    if np.any(different & ~annotation):
        raise ValueError("Recreated mask overlay differs outside ROI text annotation regions")
    np.savez_compressed(out / "effective_masks.npz", **masks)
    (out / "roi_geometry.json").write_text(json.dumps(dict(polygons=meta["polygons"],
        raw_areas=raw_areas, effective_areas=areas, regions=regions), indent=2))
    # Seek to earliest relevant event while keeping the original read-time origin.
    # The unchanged counter would otherwise scan millions of discarded pre-window events.
    def count(shift):
        earliest = actual_read + int(onsets[0]) + timing.response_delay_us + shift
        final = actual_read + int(onsets[-1]) + timing.response_delay_us + timing.response_window_us + shift
        if earliest < 0:
            raise ValueError("Shifted windows precede recording")
        with args.dat.open("rb") as f:
            f.seek(-8, 2)
            last = int.from_bytes(f.read(4), "little") - header.file_first_timestamp
        if final > last + 1:
            raise ValueError("Shifted windows exceed recording")
        pos, _, _ = find_file_position_at_timestamp(args.dat, header.data_start,
                                                   header.file_first_timestamp + earliest)
        return count_roi_flash_responses_chunked(args.dat, pos,
            header.file_first_timestamp + actual_read, actual_read, onsets + shift,
            masks, areas, header.width, header.height, timing)
    rows = count(0)
    experiment = Experiment("experiment_1d_10ms", args.dat, timing.fade_duration_us,
                            timing.dark_interval_us, timing.flash_period_us)
    peaks, repeats, estimates = estimate(rows, experiment)
    repeatability = calculate_repeatability_summary(rows)
    reproduction = {}
    for filename, table, keys in [
        ("flash_responses.csv", rows, ["roi", "repeat", "colour"]),
        ("response_vectors.csv", peaks, ["roi", "metric"]),
        ("repeatability_summary.csv", repeatability, ["roi", "colour", "metric"]),
    ]:
        reproduction[filename] = compare_saved(table, read_csv(args.saved_run / filename), keys)
        write_csv(out / filename, table)
    save_roi_response_figure(reference, polygons, rows, out / "roi_response.png")
    write_csv(out / "per_repeat_vectors.csv", repeats)
    write_csv(out / "estimator_comparison.csv", estimates)
    stage_rows = [dict(r, stage=r["colour"] + str(r["repeat"]),
                       timing_supported=support[r["colour"] + str(r["repeat"])] ) for r in rows]
    write_csv(out / "nine_stage_responses.csv", stage_rows)
    for name in masks:
        write_csv(out / f"nine_stage_{name}.csv", [r for r in stage_rows if r["roi"] == name])
    spread = []
    for name in masks:
        for colour in COLOURS:
            selected = [r for r in rows if r["roi"] == name and r["colour"] == colour]
            v = np.array([r["on_density"] for r in selected])
            cv = next(r["cv_percent"] for r in repeatability if r["roi"] == name and r["colour"] == colour and r["metric"] == "ON")
            spread.append(dict(roi=name, predicted_colour=colour, density_1=v[0], density_2=v[1], density_3=v[2],
                maximum_stage=colour + str(int(np.argmax(v)) + 1), min_density=float(v.min()),
                max_density=float(v.max()), range_density=float(np.ptp(v)), mean_density=float(v.mean()),
                median_density=float(np.median(v)), sample_CV_percent=cv,
                maximum_fraction_of_channel_ON=float(v.max() / v.sum()) if v.sum() else None))
    write_csv(out / "repetition_spread.csv", spread)
    repetition_plot(out / "same_colour_repetitions.png", stage_rows, list(masks))
    # A–D complete. The A–E baseline remains untouched by any later shift.
    bin_us = 50
    start = int(onsets[0]) + actual_read - 3000
    end = int(onsets[-1]) + actual_read + timing.response_window_us + 7000
    snapshots = [(8598565, 8599065), (8604585, 8605085), (8607585, 8608085),
                 (8599835, 8600835), (8600835, 8601835)]
    # Snapshot times are fixed observational intervals for this particular recording.
    if not (start <= min(a for a, _ in snapshots) and max(b for _, b in snapshots) <= end):
        raise ValueError("This diagnostic snapshot set requires the Experiment 1 7/9 phase")
    names, hist, images, invalid = scan_activity(args.dat, header, masks, start, end, bin_us, snapshots)
    np.savez_compressed(out / "activity_50us.npz", counts=hist, names=names,
                        start_us=start, bin_us=bin_us, snapshots=images, snapshot_intervals_us=snapshots)
    hist_rows = [dict(region=name, bin_start_us=start + i * bin_us,
                     bin_end_us=start + (i + 1) * bin_us, ON=int(v[1]), OFF=int(v[0]))
                 for j, name in enumerate(names) for i, v in enumerate(hist[j])]
    write_csv(out / "activity_50us.csv", hist_rows)
    # Independent histogram integration must exactly match existing counting functions.
    for row in rows:
        a, b = (row["window_start_us"] - start) // bin_us, (row["window_end_us"] - start) // bin_us
        if (row["window_start_us"] - start) % bin_us or (row["window_end_us"] - start) % bin_us:
            raise ValueError("Window edges must coincide with diagnostic bin edges")
        summed = hist[names.index(row["roi"]), a:b].sum(axis=0)
        np.testing.assert_array_equal(summed, [row["off"], row["on"]])
    main_stages = [r for r in stage_rows if r["roi"] == args.primary_roi]
    activity_plot(out / "global_vs_roi_activity.png", names, hist, start, bin_us,
                  main_stages, [8535000, 8620000])
    activity_plot(out / "all_nine_activity.png", names, hist, start, bin_us,
                  main_stages, [start, end])
    primary_indices = [0, names.index(args.primary_roi)]
    activity_plot(out / "transition_zoom.png", [names[i] for i in primary_indices],
                  hist[primary_indices], start, bin_us, main_stages, [8596500, 8602500])
    phases, correlations = phase_analysis(out / "within_stage_ON_profiles.png", names, hist,
                                          start, bin_us, stage_rows, areas)
    write_csv(out / "within_stage_phase.csv", phases)
    write_csv(out / "within_stage_correlations.csv", correlations)
    fractions = []
    for row in stage_rows:
        a, b = (row["window_start_us"] - start) // bin_us, (row["window_end_us"] - start) // bin_us
        whole = hist[0, a:b].sum(axis=0)
        fractions.append(dict(roi=row["roi"], stage=row["stage"],
            ROI_ON=row["on"], ROI_OFF=row["off"], global_ON=int(whole[1]), global_OFF=int(whole[0]),
            fraction_global_ON=row["on"] / whole[1] if whole[1] else None,
            fraction_global_OFF=row["off"] / whole[0] if whole[0] else None))
    write_csv(out / "roi_global_fractions.csv", fractions)
    observations = []
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), constrained_layout=True)
    for i, interval in enumerate(snapshots[:3]):
        polarity = 1 if i == 0 else 0
        frame = images[i, polarity]
        vmax = max(1, float(np.log1p(frame).max()))
        for j, image in enumerate([frame, np.where(masks[args.primary_roi], frame, 0)]):
            axes[i, j].imshow(np.log1p(image), vmin=0, vmax=vmax, cmap="magma", origin="upper")
            poly = polygons[args.primary_roi]
            closed = np.vstack([poly, poly[0]])
            axes[i, j].plot(closed[:, 0], closed[:, 1], color="cyan", lw=.6)
            axes[i, j].set_title(f"{'Global' if j == 0 else args.primary_roi} {'ON' if polarity else 'OFF'} [{interval[0]}, {interval[1]}) µs")
        for name, mask in masks.items():
            total = int(frame.sum())
            inside = int(frame[mask].sum())
            observations.append(dict(roi=name, start_us=interval[0], end_us=interval[1],
                polarity="ON" if polarity else "OFF", global_events=total, ROI_events=inside,
                fraction_inside=inside / total if total else None))
    fig.suptitle("Chosen 500 µs diagnostic intervals; log counts; cyan = unchanged primary ROI\n"
                 "Intervals do not reproduce unspecified player frame durations")
    fig.savefig(out / "observed_spatial_activity.png", dpi=140)
    plt.close(fig)
    write_csv(out / "observed_interval_fractions.csv", observations)
    transition = []
    for i, (left, right) in enumerate(snapshots[3:], 3):
        for name in names:
            frame = images[i]
            total = frame.sum(axis=(1, 2)) if name == "whole_sensor" else frame[:, masks[name]].sum(axis=1)
            transition.append(dict(region=name, start_us=left, end_us=right,
                                   ON=int(total[1]), OFF=int(total[0])))
    write_csv(out / "transition_window_counts.csv", transition)
    # Frozen-phase influence diagnostic. This is NOT filtering the actual baseline.
    influences = []
    for excluded in [("B1",), ("B3",), ("B1", "B3")]:
        subset = [r for r in rows if r["colour"] + str(r["repeat"]) not in excluded]
        derived = add_derived_measurements(subset, experiment, "FULL")
        for summary in calculate_response_summaries(derived, "ON_PEAK"):
            base = next(p for p in peaks if p["roi"] == summary["roi"])
            vector = np.array([summary[f"vector_{c}"] for c in COLOURS])
            delta = vector - [base[f"vector_{c}"] for c in COLOURS]
            influences.append(dict(summary, diagnostic_excluded_stages=",".join(excluded),
                                    L1_change=float(np.abs(delta).sum())))
    write_csv(out / "unsupported_window_influence.csv", influences)
    print("A–E complete: saved counts, densities, vectors, repeatability and non-annotation mask pixels reproduced.", flush=True)
    sensitivity_rows, sensitivity_vectors, sensitivity_repeatability = [], [], []
    if args.sensitivity:
        if max(r["cv_percent"] for r in repeatability if r["metric"] == "ON") <= 50:
            raise ValueError("No large baseline ON variation established; review before optional sensitivity")
        for shift in [-2000, -1000, -500, 0, 500, 1000, 2000]:
            shifted = rows if shift == 0 else count(shift)
            sensitivity_rows += [dict(r, artificial_shift_us=shift) for r in shifted]
            _, _, vectors = estimate(shifted, experiment)
            for r in vectors:
                base = next(e for e in estimates if e["roi"] == r["roi"] and e["estimator"] == r["estimator"])
                delta = np.array([r[f"vector_{c}"] - base[f"vector_{c}"] for c in COLOURS])
                sensitivity_vectors.append(dict(r, artificial_shift_us=shift, L1_change=float(abs(delta).sum()),
                    L2_change=float(np.linalg.norm(delta)), **{f"delta_{c}": float(delta[i]) for i, c in enumerate(COLOURS)}))
            sensitivity_repeatability += [dict(r, artificial_shift_us=shift) for r in calculate_repeatability_summary(shifted)]
        write_csv(out / "sensitivity_responses.csv", sensitivity_rows)
        write_csv(out / "sensitivity_vectors.csv", sensitivity_vectors)
        write_csv(out / "sensitivity_repeatability.csv", sensitivity_repeatability)
        fig, axes = plt.subplots(1, len(masks), figsize=(15, 4), constrained_layout=True)
        for ax, name in zip(axes, masks):
            v = [r for r in sensitivity_vectors if r["roi"] == name and r["estimator"] == "ON_PEAK"]
            for c, colour in zip(COLOURS, PALETTE):
                ax.plot([r["artificial_shift_us"] / 1000 for r in v], [r[f"vector_{c}"] for r in v],
                        marker="o", ms=3, label=c, color=colour)
            ax.axvline(0, color="black", lw=.6)
            ax.set(title=name, xlabel="Artificial window shift (ms)", ylabel="Relative ON_PEAK response", ylim=(0, 1))
        axes[0].legend()
        fig.suptitle("Sensitivity only: no shift is selected as physically correct")
        fig.savefig(out / "timing_sensitivity.png", dpi=150)
        plt.close(fig)
    sources = [Path(__file__), ROOT / "run_pipeline.py", ROOT / "run_duration_experiment.py",
               *[ROOT / "src" / name for name in ["dat_decoder.py", "flash_detection.py",
                 "temporal_alignment.py", "roi_analysis.py", "colour_mapping.py"]],
               args.saved_run / "analysis_metadata.json", args.evidence]
    manifest = dict(primary_roi=args.primary_roi, saved_run=str(args.saved_run.resolve()),
        dat=str(args.dat.resolve()), dat_bytes=args.dat.stat().st_size,
        first_DAT_timestamp_us=header.file_first_timestamp, time_origin="first DAT event",
        timing=asdict(timing), effective_areas=areas,
        mask_overlay_pixels_identical_outside_annotations=True,
        mask_figure_different_pixels_in_annotation_regions=int(different.sum()),
        reproduction=reproduction, histogram_integrations_identical=True, invalid_spatial_events=invalid,
        baseline_detector_rerun="reused verified Experiment 1 result; detector not rerun in 1D",
        original_support_labels_only=True, sensitivity_run=args.sensitivity,
        roi_selection="Saved polygons reused; CLI selects primary; all four sectors analysed",
        source_sha256={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        git_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        command=[sys.executable, *sys.argv],
        limitations=["Predicted colour identity unverified", "Only one recording and three predicted repetitions",
                     "No independent LED timings or calibrated colour reference", "500 µs snapshots are chosen diagnostic windows"])
    (out / "evidence.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
    write_report(out, args.primary_roi, stage_rows, peaks, repeats, spread, estimates,
                 fractions, observations, influences, sensitivity_vectors, sensitivity_repeatability,
                 transition, phases, correlations)
    print(f"Experiment 1D outputs: {out}", flush=True)


def write_report(out, primary, stages, peaks, repeats, spread, estimates, fractions,
                 observations, influences, sensitivity, sensitivity_repeatability,
                 transition, phases, correlations):
    lines = ["# Experiment 1D — ROI colour-response consistency", "",
        f"Primary ROI: **{primary}**. ROI_1 is the saved upper ball sector. All four saved sectors are analysed separately.",
        "No new ROI was selected. There is no whole-ball union in the baseline.", "",
        "## Reproduction and implementation", "",
        "The existing functions reproduce all 36 saved ON/OFF measurements and densities, all four ON_PEAK summaries (including display fields), all 36 repeatability rows, and the effective-mask overlay outside the ROI text annotation regions. Only annotation pixels differ in the rendered overlay; saved polygon coordinates and effective areas are reused exactly. Independent 50 µs histogram integration also reproduces all stage counts. See evidence.json for exact comparisons, source hashes and command.",
        "", "The prior Experiment 1 detector rerun is reused; the detector is not rerun or modified here. Its saved phase is 8,520,454 µs after the first DAT event. All times below share that origin. Stage labels are **predicted colours**, not independent LED identifications.",
        "", "Global phase detection uses full-sensor ON/OFF statistics, a quiet/startup comparison, fixed-schedule support and a phase-ambiguity check. It generates tj=t0+j×10500 µs here, and integrates [tj, tj+10000 µs). Polygon selection happens afterwards. The effective masks apply EXCLUDE_CONTAINED; these four have no nesting or overlaps and their areas are unchanged. ON and OFF are both counted without spatial clipping of event multiplicity, and density=count/effective pixel area.",
        "", "The colour estimator takes max ON density for each predicted colour across the three repetitions, then divides by the sum of these three maxima. OFF is retained in the exports but does not enter ON_PEAK. Global support/rejection does not filter colour measurements. Display brightness/desaturation are separate and supply no correctness evidence. Mean/median comparisons below reuse run_duration_experiment.py.",
        "", "## Nine stage measurements", ""]
    for name in sorted({r["roi"] for r in stages}):
        lines += [f"### {name}", "", "| Predicted stage | Start (µs) | End (µs) | ON count | OFF count | ON / pixel | OFF / pixel | Global timing support |",
                  "|---|---:|---:|---:|---:|---:|---:|---|"]
        for r in [s for s in stages if s["roi"] == name]:
            lines.append(f"| {r['stage']} | {r['window_start_us']} | {r['window_end_us']} | {r['on']} | {r['off']} | {r['on_density']:.8f} | {r['off_density']:.8f} | {'Supported' if r['timing_supported'] else 'Unsupported'} |")
    lines += ["", "## Repetition spread and maximum estimator", "",
              "Sample CV = 100 × sample standard deviation / mean, with ddof=1 and only three observations; this is descriptive variation, not a calibrated uncertainty estimate.", "",
              "| ROI | Predicted channel | Repetition 1 density | Repetition 2 density | Repetition 3 density | Maximum from | ON CV (%) | Maximum fraction of channel ON |",
              "|---|---|---:|---:|---:|---|---:|---:|"]
    for s in spread:
        lines.append(f"| {s['roi']} | {s['predicted_colour']} | {s['density_1']:.6f} | {s['density_2']:.6f} | {s['density_3']:.6f} | {s['maximum_stage']} | {s['sample_CV_percent']:.2f} | {s['maximum_fraction_of_channel_ON']:.2%} |")
    lines += ["", "| ROI | Estimator | Relative predicted R | Relative predicted G | Relative predicted B |", "|---|---|---:|---:|---:|"]
    for s in estimates:
        lines.append(f"| {s['roi']} | {s['estimator']} | {s['vector_R']:.6f} | {s['vector_G']:.6f} | {s['vector_B']:.6f} |")
    lines += ["", "Each repetition's sum-normalised vector is also in per_repeat_vectors.csv. The three maxima can come from different repetitions; the final vector need not describe any one RGB triplet. A stable-looking summary does not demonstrate repeatability. Median/mean are separate diagnostics, not validated improvements.",
              "", "## B1 and B3 influence", ""]
    for p in peaks:
        name = p["roi"]
        b = [r for r in stages if r["roi"] == name and r["colour"] == "B"]
        removal = next(r for r in influences if r["roi"] == name and r["diagnostic_excluded_stages"] == "B1")
        lines.append(f"- {name}: B1/B2/B3 ON counts = {b[0]['on']:,}/{b[1]['on']:,}/{b[2]['on']:,}. B{p['peak_repeat_B']} supplies the blue maximum; baseline blue component {p['vector_B']:.6f}. For a frozen-phase diagnostic excluding B1 only, blue becomes {removal['vector_B']:.6f}. B3 supplies no maximum, so excluding B3 does not change ON_PEAK; its substantial OFF response is omitted by ON_PEAK.")
    lines += ["", "These exclusions quantify estimator influence; they do not assert that globally unsupported windows are invalid ROI measurements and do not modify the baseline.",
              "", "## Global activity inside the selected ROI", "",
              "Global event fractions below are membership counts, not estimates of illumination intensity or contamination. Mask area and spatial response both affect them.", "",
              "| ROI | Predicted stage | Global ON inside ROI | Global OFF inside ROI |", "|---|---|---:|---:|"]
    for r in fractions:
        if r["roi"] == primary:
            lines.append(f"| {primary} | {r['stage']} | {r['fraction_global_ON']:.2%} | {r['fraction_global_OFF']:.2%} |")
    lines += ["", "For explicitly chosen 500 µs observational intervals:", "",
              "| Start (µs) | End (µs) | Polarity | Global events | Primary ROI events | Fraction inside |",
              "|---:|---:|---|---:|---:|---:|"]
    for o in observations:
        if o["roi"] == primary:
            lines.append(f"| {o['start_us']} | {o['end_us']} | {o['polarity']} | {o['global_events']} | {o['ROI_events']} | {o['fraction_inside']:.2%} |")
    lines += ["", "The OFF-band pattern is visible inside the unchanged primary polygon in observed_spatial_activity.png. Its physical cause remains unknown. These 500 µs intervals do not reproduce player frames of unknown duration and do not establish physical LED transition times.",
              "", "One-millisecond intervals around the reported player timestamp 8.600835 s:", "",
              "| Region | Start (µs) | End (µs) | ON | OFF |", "|---|---:|---:|---:|---:|"]
    for r in transition:
        if r["region"] in ["whole_sensor", primary]:
            lines.append(f"| {r['region']} | {r['start_us']} | {r['end_us']} | {r['ON']} | {r['OFF']} |")
    lines += ["", "The trace changes from strong ON bursts to OFF dominance in both regions. Both intervals immediately around the reported timestamp are already OFF-dominated, so 8.600835 s should not be treated as an exact transition edge. transition_zoom.png shows the surrounding 50 µs bins. The player frame convention and integration duration are not independently available here.",
              "", "## Position of responses within predicted windows", "",
              "The largest integrated 1 ms ON slice and ON-weighted centroid are descriptive response locations, not onset estimates. Each centroid uses 50 µs bin centres. A location based on only a few events is not a reliable response feature.", "",
              "| Primary predicted stage | ON count | Largest 1 ms slice begins at (µs) | ON centroid (µs) |",
              "|---|---:|---:|---:|"]
    for r in phases:
        if r["roi"] == primary:
            centroid = f"{r['ON_weighted_centroid_us']:.1f}" if r["ON_weighted_centroid_us"] is not None else "undefined"
            lines.append(f"| {r['stage']} | {r['ON']} | {r['peak_1ms_slice_start_us'] if r['ON'] else 'undefined'} | {centroid} |")
    primary_corr = [r["log_ON_profile_correlation"] for r in correlations if r["roi"] == primary and r["log_ON_profile_correlation"] is not None]
    lines += ["", f"Nonconstant pairwise log-ON profile correlations for the primary ROI range from {min(primary_corr):.3f} to {max(primary_corr):.3f}; zero/constant profiles have undefined correlations. The strong responses are not consistently located at the same relative stage positions. All sectors' phase summaries and profile correlations are exported separately.",
              "", "![Whole sensor and saved ROIs](global_vs_roi_activity.png)",
              "", "![All nine responses](same_colour_repetitions.png)",
              "", "![Within-stage ON profiles](within_stage_ON_profiles.png)"]
    if sensitivity:
        lines += ["", "## Artificial shift sensitivity", "",
                  "Performed after A–E established large ON variation. Every mask, integration duration, stage spacing and estimator is held fixed; all shifted windows fit the recording. Original support labels are not rescored. These are artificial perturbations, not candidate physical LED alignments.",
                  "", f"For {primary}:", "", "| Shift (ms) | ON_PEAK R | ON_PEAK G | ON_PEAK B | L1 vector change | ON CV R/G/B (%) |", "|---:|---:|---:|---:|---:|---|"]
        for s in sensitivity:
            if s["roi"] == primary and s["estimator"] == "ON_PEAK":
                cv = [next(r["cv_percent"] for r in sensitivity_repeatability if r["roi"] == primary and r["colour"] == c and r["metric"] == "ON" and r["artificial_shift_us"] == s["artificial_shift_us"]) for c in COLOURS]
                lines.append(f"| {s['artificial_shift_us'] / 1000:+g} | {s['vector_R']:.6f} | {s['vector_G']:.6f} | {s['vector_B']:.6f} | {s['L1_change']:.6f} | {cv[0]:.2f}/{cv[1]:.2f}/{cv[2]:.2f} |")
        lines += ["", "All ROIs, repetitions, ON/OFF counts, densities, estimator vectors, signed component changes and repeatability are exported in sensitivity_*.csv. No shift is selected as correct.", "", "![Timing sensitivity](timing_sensitivity.png)"]
    lines += ["", "## Answers and next priority", "",
              "1. **Extraction functions as implemented:** exact reproduction and independent histogram checks support counting, mask membership, area normalisation and ON_PEAK arithmetic. This does not validate the physical colour labels.",
              "2. **Same-colour repetitions are not reasonably repeatable in this saved sequence:** see large ON CVs and the individual rows; no statistical acceptance threshold is inferred from three repeats.",
              "3. **B1/B3 influence is ROI-dependent:** B1 sets some blue maxima, while other sectors use B2. B3 has almost no ON response and does not set a blue maximum, but its OFF response remains substantial.",
              "4. **The maximum summary conceals variation if reported alone:** it discards the two smaller responses per channel. The existing repeatability and per-repeat exports reveal this variation when examined.",
              "5. **Some unusual activity lies inside the selected polygon:** membership fractions and spatial snapshots quantify it; outside events cannot directly enter the ROI counter. Global statistics can still affect its predicted timing.",
              "6. **These predicted windows yield unstable ROI measurements:** repetition/profile variation and the optional phase perturbation quantify instability. They do not isolate timing error from optical variation, motion, or other camera-response effects.",
              "7. **Unresolved:** physical RGB identity, actual LED edges, optical waveform, clock relation, sensor response latency and absolute colour accuracy. Event peaks alone cannot resolve them.",
              "", "**Next priority: independently measure the illumination and its timing relative to camera events, then evaluate temporal validation against that reference.** Preserve this fixed-schedule baseline. No evidence here requires reimplementing ROI extraction or choosing a new RGB period. Calibrated colour evaluation follows a validated timing reference; adjusting summary estimators alone does not establish correct colour."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
