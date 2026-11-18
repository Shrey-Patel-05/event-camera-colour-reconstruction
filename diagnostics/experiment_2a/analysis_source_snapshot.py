"""Experiment 2A: unchanged timing models, one shared upper-ball ROI, three DATs.

Reruns the available detector on the two additional recordings. Independent
PSEELoader histograms cover each full recording and cross-check the saved global
overview and the exact nine-stage ROI counts. See docs/experiment_2a.md.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from dat_decoder import read_dat_header, find_file_position_at_timestamp
from flash_detection import detect_flash_onsets_chunked, FlashSearchConfig
from temporal_alignment import TimingConfig, build_fixed_flash_onsets
from roi_analysis import (make_roi_masks, count_roi_flash_responses_chunked,
                          calculate_repeatability_summary, save_effective_roi_mask_figure, write_csv)
from colour_mapping import build_roi_colours, ColourConfig
from run_duration_experiment import Experiment, add_derived_measurements, calculate_response_summaries
from run_raw_diagnostic import load_psee
from run_roi_consistency import read_csv, compare_saved, activity_plot, repetition_plot

SAVED = ROOT / "new_led_full_recording_results"
CASES = [("1ms_2s", SAVED / "1ms_2s/20261022_141535_799356"),
         ("10ms_4s", SAVED / "10ms_4s/20261022_125050_727915"),
         ("100ms_10s", SAVED / "example/20261021_174732_769337")]
REGION = "COMMON_UPPER"
COLOURS = ("R", "G", "B")


def lag_correlations(counts, lags):
    """FFT cross-products with separate per-polarity overlap means at each lag.

    Equivalent to centring each overlapping log1p ON/OFF segment separately,
    then taking a single normalised dot product of the two flattened arrays.
    """
    x = np.log1p(np.asarray(counts, dtype=float))
    n = len(x)
    lags = np.asarray(lags, dtype=int)
    if np.any(lags <= 0) or np.any(lags >= n):
        raise ValueError("Lags must lie strictly between zero and segment length")
    fft_n = 1 << (2 * n - 1).bit_length()
    transformed = np.fft.rfft(x, n=fft_n, axis=0)
    products = np.fft.irfft(transformed.conj() * transformed, n=fft_n, axis=0)[:n].sum(axis=1)
    prefix = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x, axis=0)])
    squares = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(x * x, axis=0)])
    m = (n - lags)[:, None]
    sa, sb = prefix[n - lags], prefix[n] - prefix[lags]
    qa, qb = squares[n - lags], squares[n] - squares[lags]
    va = (qa - sa * sa / m).sum(axis=1)
    vb = (qb - sb * sb / m).sum(axis=1)
    denominator = np.sqrt(np.maximum(0, va) * np.maximum(0, vb))
    numerator = products[lags] - (sa * sb / m).sum(axis=1)
    result = np.full(len(lags), np.nan)
    valid = (va > 1e-10 * np.maximum(1, qa.sum(axis=1))) & (vb > 1e-10 * np.maximum(1, qb.sum(axis=1)))
    result[valid] = np.clip(numerator[valid] / denominator[valid], -1, 1)
    return result


def full_raw_scan(dat, header, mask, onsets, window_us, toolbox):
    loader = load_psee(toolbox)(str(dat.resolve()))
    last = int(loader.total_time()) - header.file_first_timestamp
    n = (last + 1 + 49) // 50
    hist = np.zeros((2, n, 2), dtype=np.int64)  # global/common ROI, time, OFF/ON
    stage_counts = np.zeros((9, 2, 2), dtype=np.int64)
    previous = None
    total, invalid = 0, 0
    last_update = time.monotonic()
    try:
        while not loader.done:
            events = loader.load_n_events(1_000_000)
            if not len(events):
                break
            t = events["t"].astype(np.int64) - header.file_first_timestamp
            if (previous is not None and t[0] < previous) or np.any(np.diff(t) < 0):
                raise ValueError("PSEELoader timestamps decreased")
            previous = int(t[-1])
            x, y, p = events["x"].astype(int), events["y"].astype(int), events["p"].astype(int)
            valid = (x >= 0) & (x < header.width) & (y >= 0) & (y < header.height)
            invalid += int((~valid).sum())
            inside = np.zeros(len(t), dtype=bool)
            inside[valid] = mask[y[valid], x[valid]]
            bins = t // 50
            lo, hi = int(bins[0]), int(bins[-1]) + 1
            flat = (bins - lo) * 2 + p
            hist[0, lo:hi] += np.bincount(flat, minlength=(hi - lo) * 2).reshape(-1, 2)
            hist[1, lo:hi] += np.bincount(flat[inside], minlength=(hi - lo) * 2).reshape(-1, 2)
            for i, onset in enumerate(onsets):
                left, right = np.searchsorted(t, [onset, onset + window_us], side="left")
                if right > left:
                    stage_counts[i, 0] += np.bincount(p[left:right], minlength=2)
                    stage_counts[i, 1] += np.bincount(p[left:right][inside[left:right]], minlength=2)
            total += len(t)
            if time.monotonic() - last_update >= 3:
                print(f"{dat.stem}: raw {total:,} events, {previous / 1e6:.2f}s", flush=True)
                last_update = time.monotonic()
    finally:
        loader._file.close()
    return hist, stage_counts, last + 1, invalid


def quantify(rows, experiment, mode):
    # Neutral display parameters: quantitative vectors precede display scaling.
    neutral = {REGION: dict(raw_brightness_ratio=1.0, display_brightness_multiplier=1.0)}
    _, peaks, repeat_vectors = build_roi_colours(rows, neutral, ColourConfig())
    derived = add_derived_measurements(rows, experiment, mode)
    estimates = [r for method in ("ON_PEAK", "ON_MEAN", "ON_MEDIAN")
                 for r in calculate_response_summaries(derived, method)]
    for r in estimates:
        r["nonzero_vector"] = bool(sum(r[f"amplitude_{c}_density"] for c in COLOURS) > 0)
    return peaks, repeat_vectors, estimates


def periodicity(hist, duration, t0, cycle, out):
    # Drop only the final incomplete 500 µs envelope bin.
    env = hist[:, :duration // 500 * 10].reshape(2, -1, 10, 2).sum(axis=2)
    tail = duration - t0
    sections = [("whole_recording", 0, duration),
                ("around_selected_phase", max(0, t0 - 500_000), min(duration, t0 + 3_000_000))]
    step = tail // 3
    for i in range(3):
        sections.append((f"post_phase_third_{i + 1}", t0 + i * step,
                         min(duration, t0 + i * step + min(4_000_000, step))))
    curves, summaries = [], []
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True, sharex=True)
    for region, ax in zip(range(2), axes):
        for section, left, right in sections:
            a, b = (left + 499) // 500, right // 500
            counts = env[region, a:b]
            max_lag = min(2_000_000 // 500, len(counts) // 3)
            lags = np.arange(10, max_lag + 1)  # 5 ms minimum avoids near-zero smoothness.
            if not len(lags):
                continue
            corr = lag_correlations(counts, lags)
            configured_lag = round(cycle / 500)
            configured = float(lag_correlations(counts, [configured_lag])[0]) if configured_lag < len(counts) else float("nan")
            best = int(np.nanargmax(corr)) if np.isfinite(corr).any() else None
            # Export up to five separated interior local maxima as potential harmonics.
            peaks = np.flatnonzero((corr[1:-1] > corr[:-2]) & (corr[1:-1] >= corr[2:])) + 1
            selected = []
            for index in sorted(peaks, key=lambda j: corr[j], reverse=True):
                if all(abs(int(lags[index]) - int(lags[k])) >= 10 for k in selected):
                    selected.append(index)
                if len(selected) == 5:
                    break
            summaries.append(dict(region="whole_sensor" if region == 0 else REGION,
                section=section, start_us=a * 500, end_us=b * 500,
                configured_RGB_cycle_us=cycle, tested_cycle_lag_us=configured_lag * 500,
                configured_cycle_correlation=configured,
                strongest_searched_lag_us=int(lags[best] * 500) if best is not None else None,
                strongest_searched_correlation=float(corr[best]) if best is not None else None,
                search_min_us=5000, search_max_us=max_lag * 500,
                local_peak_lags_us=",".join(str(int(lags[k] * 500)) for k in selected),
                local_peak_correlations=",".join(f"{corr[k]:.6f}" for k in selected)))
            curves += [dict(region="whole_sensor" if region == 0 else REGION, section=section,
                            lag_us=int(lag * 500), correlation=float(value)) for lag, value in zip(lags, corr)]
            ax.plot(lags * .5, corr, lw=.7, label=section)
        ax.axvline(cycle / 1000, color="black", linestyle="--", label="configured cycle")
        ax.set(title="Whole sensor" if region == 0 else REGION,
               ylabel="Log ON/OFF envelope correlation", ylim=(-1, 1))
        ax.legend(fontsize=7, ncol=2)
    axes[-1].set_xlabel("Lag (ms); 500 µs envelope and lag resolution")
    fig.suptitle("Event recurrence and possible harmonics; not measured LED timing")
    fig.savefig(out / "recurrence.png", dpi=150)
    plt.close(fig)
    write_csv(out / "recurrence_curves.csv", curves)
    write_csv(out / "recurrence_summary.csv", summaries)
    return summaries


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolbox", type=Path, default=ROOT.parent / "prophesee-automotive-dataset-toolbox")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    geometry_meta = json.loads((CASES[2][1] / "analysis_metadata.json").read_text())
    polygons = {REGION: np.asarray(geometry_meta["polygons"]["ROI_1"], dtype=np.int32)}
    comparison, all_repeatability, all_estimates, all_sensitivity, manifests = [], [], [], [], []
    fig_rois, roi_axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    for case_i, (name, saved) in enumerate(CASES):
        out = args.output / name
        out.mkdir()
        dat = ROOT / "data" / (name + ".dat")
        header = read_dat_header(dat)
        masks, areas = make_roi_masks(polygons, header.width, header.height)
        reference = cv2.imread(str(saved / "roi_reference.png"), cv2.IMREAD_GRAYSCALE)
        if reference is None:
            raise ValueError(f"Missing reference image for {name}")
        save_effective_roi_mask_figure(reference, polygons, masks, out / "common_roi_overlay.png")
        roi_axes[case_i].imshow(reference, cmap="gray", vmin=0, vmax=255)
        closed = np.vstack([polygons[REGION], polygons[REGION][0]])
        roi_axes[case_i].plot(closed[:, 0], closed[:, 1], color="cyan", lw=1)
        roi_axes[case_i].set_title(name)
        roi_axes[case_i].set_axis_off()
        saved_report = json.loads((saved / "automatic_timing_report.json").read_text())
        retained = 4_500_004 if name == "10ms_4s" else 0
        first = retained + int(saved_report["first_onset_after_sync_us"])
        duration_us = saved_report["fade_duration_us"]
        timing = TimingConfig(**{k: v for k, v in saved_report.items() if k in TimingConfig.__dataclass_fields__},
                              **({} if "response_window_us" in saved_report else {"response_window_us": duration_us}))
        expected = build_fixed_flash_onsets(first, timing)
        summary = json.loads((saved / "recording_summary.json").read_text())
        with dat.open("rb") as f:
            f.seek(-8, 2)
            last = int.from_bytes(f.read(4), "little") - header.file_first_timestamp
        event_count = (dat.stat().st_size - header.data_start) // 8
        identity_summary = json.loads((SAVED / "10ms_4s/20261022_125851_330700/recording_summary.json").read_text()) if retained else summary
        if event_count != identity_summary["events"] or last != identity_summary["retained_event_span_us"]:
            raise ValueError("Recording identity differs from saved global summary")
        if name != "10ms_4s":
            print(f"{name}: rerunning unchanged detector", flush=True)
            detection = detect_flash_onsets_chunked(dat, header.data_start,
                header.file_first_timestamp, 0, out / "pipeline", timing, FlashSearchConfig())
            if not np.array_equal(detection.onsets_us, expected):
                raise ValueError(f"{name}: detector did not reproduce saved phase")
            checks = read_csv(out / "pipeline/automatic_timing_check.csv")
            compare_saved(checks, read_csv(saved / "automatic_timing_check.csv"), ["stage"])
        else:
            checks = read_csv(saved / "automatic_timing_check.csv")
            previous = json.loads((ROOT / "diagnostics/experiment_1_10ms/evidence.json").read_text())
            if previous["rerun_onsets_after_file_first_us"] != expected.tolist():
                raise ValueError("10 ms verified baseline phase differs")
        support = {c["stage"]: c["supported"].lower() == "true" for c in checks}
        experiment = Experiment(name, dat, duration_us, timing.dark_interval_us, timing.flash_period_us)
        def count(shift=0, window=None):
            cfg = timing if window is None else replace(timing, response_window_us=window)
            onsets = expected + shift
            if onsets[0] < 0 or onsets[-1] + cfg.response_window_us > last + 1:
                raise ValueError("Perturbed windows fall outside recording")
            pos, _, _ = find_file_position_at_timestamp(dat, header.data_start,
                                                       header.file_first_timestamp + int(onsets[0]))
            return count_roi_flash_responses_chunked(dat, pos, header.file_first_timestamp,
                0, onsets, masks, areas, header.width, header.height, cfg)
        rows = count()
        native_check = None
        if name == "100ms_10s":
            native = [dict(r, roi="ROI_1") for r in rows]
            native_check = compare_saved(native, read_csv(saved / "flash_responses.csv"), ["roi", "repeat", "colour"])
        write_csv(out / "flash_responses.csv", rows)
        labelled = [dict(r, stage=r["colour"] + str(r["repeat"]),
                         timing_supported=support[r["colour"] + str(r["repeat"])]) for r in rows]
        write_csv(out / "nine_stage_responses.csv", labelled)
        write_csv(out / "timing_support.csv", checks)
        repetition_plot(out / "same_colour_repetitions.png", labelled, [REGION])
        peaks, repeat_vectors, estimates = quantify(rows, experiment, "FULL")
        write_csv(out / "response_vectors.csv", peaks)
        write_csv(out / "per_repeat_vectors.csv", repeat_vectors)
        methods = []
        full_repeatability = calculate_repeatability_summary(rows)
        for mode, measured in [("FULL", rows), ("FIXED_500US", count(window=500))]:
            _, _, est = quantify(measured, experiment, mode)
            rep = calculate_repeatability_summary(measured)
            all_repeatability += [dict(r, recording=name, window_mode=mode) for r in rep]
            all_estimates += [dict(r, recording=name) for r in est]
            methods += est
        write_csv(out / "estimator_comparison.csv", methods)
        write_csv(out / "repeatability_summary.csv", full_repeatability)
        print(f"{name}: independent full-recording PSEELoader scan", flush=True)
        hist, raw_stage, duration, invalid = full_raw_scan(dat, header, masks[REGION], expected,
                                                         timing.response_window_us, args.toolbox)
        for i, row in enumerate(rows):
            np.testing.assert_array_equal(raw_stage[i, 1], [row["off"], row["on"]])
            np.testing.assert_array_equal(raw_stage[i, 0, 1], float(checks[i]["ramp_ON"]))
        # The old 10 ms overview starts at +4,500,004 µs; use the zero-skip
        # overview saved separately for a common first-event-relative grid.
        coarse_saved = SAVED / "10ms_4s/20261022_125851_330700" if retained else saved
        coarse = read_csv(coarse_saved / "initial_activity.csv")
        factor = 1000 // 50
        padded = np.pad(hist[0], ((0, (-hist.shape[1]) % factor), (0, 0)))
        np.testing.assert_array_equal(padded.reshape(-1, factor, 2).sum(axis=1),
                                     np.array([[int(c["OFF"]), int(c["ON"])] for c in coarse]))
        np.savez_compressed(out / "raw_activity_50us.npz", counts=hist, bin_us=50,
                            start_us=0, duration_us=duration, region=REGION, stage_counts=raw_stage)
        limits = [max(0, first - max(2000, timing.flash_period_us // 2)),
                  min(duration, int(expected[-1]) + timing.flash_period_us + max(2000, timing.flash_period_us // 2))]
        activity_plot(out / "aligned_activity.png", ["whole_sensor", REGION], hist, 0, 50, labelled, limits)
        recurrence = periodicity(hist, duration, first, 3 * timing.flash_period_us, out)
        selected_recurrence = next(r for r in recurrence if r["region"] == "whole_sensor" and r["section"] == "around_selected_phase")
        baseline_peak = next(e for e in estimates if e["estimator"] == "ON_PEAK")
        median = next(e for e in estimates if e["estimator"] == "ON_MEDIAN")
        peak_median_l1 = sum(abs(baseline_peak[f"vector_{c}"] - median[f"vector_{c}"]) for c in COLOURS)
        shifts = {}
        if args.sensitivity:
            schemes = {"absolute_us": [-2000, -1000, -500, 0, 500, 1000, 2000],
                       "fraction_of_fade": [round(duration_us * fraction) for fraction in [-.2, -.1, -.05, 0, .05, .1, .2]]}
            shifted_rows = []
            shifted_rep = []
            for shift in sorted(set(sum(schemes.values(), []))):
                measured = rows if shift == 0 else count(shift)
                shifts[shift] = quantify(measured, experiment, "FULL")[2]
                shifted_rows += [dict(r, artificial_shift_us=shift) for r in measured]
                shifted_rep += [dict(r, artificial_shift_us=shift) for r in calculate_repeatability_summary(measured)]
            for scheme, values in schemes.items():
                for shift in values:
                    for e in shifts[shift]:
                        base = next(b for b in estimates if b["estimator"] == e["estimator"])
                        all_sensitivity.append(dict(e, recording=name, scheme=scheme, artificial_shift_us=shift,
                            shift_fraction_of_fade=shift / duration_us,
                            L1_change=sum(abs(e[f"vector_{c}"] - base[f"vector_{c}"]) for c in COLOURS)))
            write_csv(out / "sensitivity_responses.csv", shifted_rows)
            write_csv(out / "sensitivity_repeatability.csv", shifted_rep)
        cv = {c: next(r["cv_percent"] for r in full_repeatability if r["metric"] == "ON" and r["colour"] == c) for c in COLOURS}
        comparison.append(dict(recording=name, configured_fade_us=duration_us,
            configured_RGB_cycle_us=3 * timing.flash_period_us, selected_phase_us=first,
            retained_start_us=retained, supported_windows=sum(support.values()),
            failed_windows=",".join(k for k, v in support.items() if not v),
            ROI_area_pixels=areas[REGION], ROI_ON_total=sum(r["on"] for r in rows),
            ROI_OFF_total=sum(r["off"] for r in rows), **{f"ON_CV_{c}_percent": cv[c] for c in COLOURS},
            **{f"ON_PEAK_{c}": baseline_peak[f"vector_{c}"] for c in COLOURS},
            peak_median_L1=peak_median_l1,
            selected_context_best_lag_us=selected_recurrence["strongest_searched_lag_us"],
            selected_context_best_correlation=selected_recurrence["strongest_searched_correlation"],
            selected_context_configured_cycle_correlation=selected_recurrence["configured_cycle_correlation"]))
        manifests.append(dict(recording=name, dat=str(dat), dat_bytes=dat.stat().st_size,
            first_DAT_timestamp_us=header.file_first_timestamp, header_lines=header.header_lines,
            events=int(hist[0].sum()), duration_us=duration, timing=asdict(timing),
            saved_run=str(saved), archived_name="data/example.dat" if name == "100ms_10s" else str(dat),
            detector_reproduced=True, detector_rerun_this_experiment=name != "10ms_4s",
            PSEE_global_counts_match_every_saved_1ms_bin=True,
            PSEE_stage_counts_match_existing_counter=True,
            native_100ms_response_reproduction=native_check, invalid_spatial_events=invalid))
    fig_rois.suptitle("Identical COMMON_UPPER polygon on saved reference frames; visual placement check only")
    fig_rois.savefig(args.output / "common_roi_comparison.png", dpi=150)
    plt.close(fig_rois)
    write_csv(args.output / "comparison.csv", comparison)
    write_csv(args.output / "channel_repeatability.csv", all_repeatability)
    write_csv(args.output / "estimator_comparison.csv", all_estimates)
    write_csv(args.output / "sensitivity_vectors.csv", all_sensitivity)
    np.savez_compressed(args.output / "common_mask.npz", **masks)
    source_files = [Path(__file__), ROOT / "run_roi_consistency.py", ROOT / "run_raw_diagnostic.py",
                    ROOT / "run_duration_experiment.py", *sorted((ROOT / "src").glob("*.py")),
                    args.toolbox / "src/io/psee_loader.py", args.toolbox / "src/io/dat_events_tools.py"]
    manifest = dict(cases=manifests, shared_polygon=polygons[REGION].tolist(),
        shared_polygon_source=str(CASES[2][1] / "analysis_metadata.json"),
        original_1ms_ROI_coordinates_unavailable=True,
        original_10ms_ROI1_area=188526, shared_area=areas[REGION],
        source_sha256={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        command=[sys.executable, *sys.argv],
        git_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    (args.output / "evidence.json").write_text(json.dumps(clean(manifest), indent=2, allow_nan=False))
    summary_plots(args.output, comparison, all_estimates, all_sensitivity)
    report(args.output, comparison, all_estimates, all_sensitivity)
    print(json.dumps(clean(comparison), indent=2), flush=True)


def summary_plots(out, comparison, estimates, sensitivity):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    x = np.arange(3)
    for i, c in enumerate(COLOURS):
        axes[0].bar(x + (i - 1) * .25, [r[f"ON_CV_{c}_percent"] for r in comparison],
                    width=.25, label=f"predicted {c}")
    axes[0].set_xticks(x, [r["recording"] for r in comparison])
    axes[0].set(ylabel="ON CV (%) — three repetitions", title="Full configured response windows")
    axes[0].legend()
    for i, row in enumerate(comparison):
        for j, mode in enumerate(["FULL", "FIXED_500US"]):
            p = next(r for r in estimates if r["recording"] == row["recording"] and r["window_mode"] == mode and r["estimator"] == "ON_PEAK")
            m = next(r for r in estimates if r["recording"] == row["recording"] and r["window_mode"] == mode and r["estimator"] == "ON_MEDIAN")
            axes[1].bar(i + (j - .5) * .35, sum(abs(p[f"vector_{c}"] - m[f"vector_{c}"]) for c in COLOURS),
                        width=.35, color=["tab:blue", "tab:orange"][j],
                        label=mode if i == 0 else None)
    axes[1].set_xticks(x, [r["recording"] for r in comparison])
    axes[1].set(ylabel="L1 difference: ON_PEAK vs ON_MEDIAN", title="Estimator dependence (zero vectors flagged in CSV)")
    axes[1].legend()
    fig.savefig(out / "repeatability_and_estimators.png", dpi=150)
    plt.close(fig)
    if sensitivity:
        fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
        for ax, row in zip(axes, comparison):
            for scheme in ["absolute_us", "fraction_of_fade"]:
                values = [r for r in sensitivity if r["recording"] == row["recording"] and r["scheme"] == scheme and r["estimator"] == "ON_PEAK"]
                ax.plot([r["shift_fraction_of_fade"] for r in values], [r["L1_change"] for r in values],
                        marker="o", ms=3, label=scheme)
            ax.set(title=row["recording"], xlabel="Artificial shift / configured fade", ylabel="ON_PEAK L1 change from baseline")
            ax.legend(fontsize=8)
        fig.suptitle("Absolute shifts can cross stages in the 1 ms model; no shift selected as correct")
        fig.savefig(out / "timing_sensitivity.png", dpi=150)
        plt.close(fig)


def report(out, comparison, estimates, sensitivity):
    def fmt(v, digits=3):
        return f"{v:.{digits}f}" if v is not None and np.isfinite(v) else "undefined"
    lines = ["# Experiment 2A — cross-recording repeatability", "",
        "All labels are predicted illumination colours. No configured RGB period, detector or colour-mapping algorithm was changed.",
        "", "## Shared ROI and provenance", "",
        "COMMON_UPPER is the saved 169,996-pixel upper-ball polygon from the 100 ms archive. Its coordinates are identical across recordings. This is a diagnostic ROI transfer with a visual overlay check, not verified pixel/material registration. It differs from Experiment 1D's 188,526-pixel ROI_1. Original 1D outputs remain intact. The 1 ms archive lacks ROI coordinates/response CSVs, so no reproduction of its original spatial selection is claimed.",
        "", "The 100 ms archive says data/example.dat. Its event count, span, complete saved 1 ms global histogram and native ROI counts agree with 100ms_10s.dat. The 1 ms and 100 ms unchanged detectors were rerun and reproduced saved onsets and per-stage support scores. The 10 ms 7/9 case reuses the previously verified phase after its original 4.5 s skip; the two other searches start at the beginning. Different search histories remain a confound.",
        "", "Independent PSEELoader decoding covers all three full recordings. Every saved 1 ms OFF/ON global bin and every exact FULL ROI stage count agrees with the project reader/counter. See evidence.json. The 100 ms native ROI response CSV is also reproduced. Sparse/zero ON counts are reported; undefined CVs and zero-sum vectors must not be interpreted as stable colour estimates.",
        "", "![Identical polygon placement](common_roi_comparison.png)",
        "", "## FULL response-window comparison", "",
        "| Recording | Configured RGB cycle (ms) | Supported | Failed predicted stages | ROI ON / OFF total | ON CV R/G/B (%) | Peak–median L1 |",
        "|---|---:|---:|---|---:|---|---:|"]
    for r in comparison:
        lines.append(f"| {r['recording']} | {r['configured_RGB_cycle_us'] / 1000:g} | {r['supported_windows']}/9 | {r['failed_windows']} | {r['ROI_ON_total']:,} / {r['ROI_OFF_total']:,} | {' / '.join(fmt(r[f'ON_CV_{c}_percent'], 2) for c in COLOURS)} | {r['peak_median_L1']:.6f} |")
    lines += ["", "| Recording | Window mode | Estimator | Relative predicted R | G | B | Nonzero vector |", "|---|---|---|---:|---:|---:|---|"]
    for r in estimates:
        lines.append(f"| {r['recording']} | {r['window_mode']} | {r['estimator']} | {r['vector_R']:.6f} | {r['vector_G']:.6f} | {r['vector_B']:.6f} | {r['nonzero_vector']} |")
    lines += ["", "FULL uses the configured 1/10/100 ms response duration. FIXED_500US is a separate existing-framework diagnostic: the first 500 µs after each predicted onset, with identical masks/spacing/phase and original global support labels. Channel_repeatability.csv contains ON, OFF and TOTAL CVs for both window modes. Equal 500 µs intervals control integration duration but may sample different response phases; they do not validate LED timing.",
        "", "![Repeatability and estimator dependence](repeatability_and_estimators.png)",
        "", "## Event recurrence", "",
        "500 µs log ON/OFF envelopes, centred independently per polarity at each lag. Correlations describe event recurrence, not RGB identity. Broad search starts at 5 ms to avoid near-zero smoothness and ends at min(2 s, one third of the section). The configured cycle is also tested separately, including the 4.5 ms model. Interior local maxima and possible harmonics are exported; the strongest lag is not necessarily a unique period.",
        "", "Five deterministic sections per recording: whole file, t0−0.5 to t0+3 s, and up to 4 s from each third of the remaining post-phase stream. Boundaries are trimmed to complete 500 µs bins. Whole-file statistics can mix startup, inactive and active regimes; inspect section agreement and the plots.",
        "", "| Recording | Selected context strongest searched lag (ms) | Correlation | Correlation at configured RGB cycle |", "|---|---:|---:|---:|"]
    for r in comparison:
        lines.append(f"| {r['recording']} | {fmt(r['selected_context_best_lag_us'] / 1000 if r['selected_context_best_lag_us'] else None, 1)} | {fmt(r['selected_context_best_correlation'])} | {fmt(r['selected_context_configured_cycle_correlation'])} |")
    lines += ["", "## Artificial timing shifts", "",
        "Two explicitly separate schemes use unchanged FULL windows: absolute −2/−1/−0.5/0/+0.5/+1/+2 ms; and −20/−10/−5/0/+5/+10/+20% of configured fade duration. The absolute ±2 ms shifts exceed the 1 ms stage spacing and are not small local errors for that model. Per-stage counts, densities, repeatability and estimator vectors are exported. Support scores are not recomputed for artificial shifts. No shift is selected as correct."]
    if sensitivity:
        lines += ["", "| Recording | Scheme | Maximum tested ON_PEAK L1 change |", "|---|---|---:|"]
        for r in comparison:
            for scheme in ["absolute_us", "fraction_of_fade"]:
                values = [s["L1_change"] for s in sensitivity if s["recording"] == r["recording"] and s["scheme"] == scheme and s["estimator"] == "ON_PEAK"]
                lines.append(f"| {r['recording']} | {scheme} | {max(values):.6f} |")
        lines += ["", "![Artificial shift sensitivity](timing_sensitivity.png)"]
    lines += ["", "## Interpretation limits", "",
        "One recording per nominal duration, one selected nine-stage sequence, unverified physical RGB identity, different detector search histories, possible spatial misregistration and changing integration duration prevent a causal ranking of illumination-duration robustness. Low event counts can yield zero medians, undefined CVs or highly variable normalised vectors. Lower CV alone does not establish a useful colour response. Hardware timings and colour ground truth remain unmeasured.",
        "", "The original ROI counting, ON_PEAK rule and existing mean/median estimators are reused. Global support does not filter ROI measurements. Use the nine_stage_responses.csv and plots in each recording directory to interpret support failures directly.",
        "", "For the evidence-based interpretation and reproduction commands, see docs/experiment_2a.md in the repository."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
