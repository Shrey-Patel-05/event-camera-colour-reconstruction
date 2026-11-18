"""Experiment 1: independent PSEELoader evidence against an unchanged detector.

All exported times are microseconds after the FIRST DAT EVENT, not after a
seek and not absolute DAT timestamps. No smoothing/thresholding is used for
the raw counts. See docs/experiment_1.md for a reproducible example.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from dat_decoder import (read_dat_header, find_file_position_at_timestamp,
                         scan_polarity_bins)
from temporal_alignment import TimingConfig, TimingDetectionError
from flash_detection import FlashSearchConfig, detect_flash_onsets_chunked


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_psee(toolbox):
    # A private package name prevents collision with this project's src package.
    spec = importlib.util.spec_from_file_location(
        "diagnostic_psee_io", toolbox / "src/io/__init__.py",
        submodule_search_locations=[str(toolbox / "src/io")])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    from diagnostic_psee_io.psee_loader import PSEELoader
    return PSEELoader


def correlation(counts, lag):
    """Log envelopes, each polarity centred independently; no colour labels."""
    a, b = np.log1p(counts[:-lag]), np.log1p(counts[lag:])
    a -= a.mean(axis=0)
    b -= b.mean(axis=0)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.sum(a * b) / denominator) if denominator else None


def raw_scan(loader, first, start, end, bin_us, onsets, width_us):
    height, width = loader.get_size()
    n = (end - start + bin_us - 1) // bin_us
    counts = np.zeros((n, 2), dtype=np.int64)
    maps = np.zeros((len(onsets), 2, height, width), dtype=np.int64)
    invalid = 0
    previous = None
    loader.seek_time(first + start)
    while not loader.done:
        events = loader.load_n_events(1_000_000)
        if not len(events):
            break
        t = events["t"].astype(np.int64) - first
        if (previous is not None and t[0] < previous) or np.any(np.diff(t) < 0):
            raise ValueError("Raw timestamps decrease; unwrap before analysis.")
        previous = int(t[-1])
        keep = (t >= start) & (t < end)
        selected = events[keep]
        t = t[keep]
        p = selected["p"].astype(np.int64)
        if np.any((p < 0) | (p > 1)):
            raise ValueError("Unexpected polarity encoding")
        flat = ((t - start) // bin_us) * 2 + p
        counts += np.bincount(flat, minlength=n * 2).reshape(n, 2)
        x, y = selected["x"].astype(int), selected["y"].astype(int)
        valid = (x >= 0) & (x < width) & (y >= 0) & (y < height)
        invalid += int((~valid).sum())
        for i, onset in enumerate(onsets):
            mask = valid & (t >= onset) & (t < onset + width_us)
            pixels = p[mask] * height * width + y[mask] * width + x[mask]
            maps[i] += np.bincount(pixels, minlength=2 * height * width).reshape(
                2, height, width)
        if previous >= end:
            break
    return counts, maps, invalid


def plot_activity(path, counts, start, bin_us, onsets, checks, duration, limits):
    t = (start + np.arange(len(counts)) * bin_us) / 1000
    fig, axes = plt.subplots(3, 1, figsize=(15, 8), sharex=True,
                             constrained_layout=True)
    for ax, values, label in zip(axes, [counts.sum(axis=1), counts[:, 1],
                                       counts[:, 0]], ["Total", "ON", "OFF"]):
        ax.step(t, values, where="post", lw=.65, color="black")
        ax.set_ylabel(f"{label} / {bin_us} µs")
        ax.set_yscale("symlog", linthresh=10)
        for onset, check in zip(onsets, checks):
            if onset + duration < limits[0] or onset > limits[1]:
                continue
            supported = str(check["supported"]).lower() == "true"
            colour = "tab:green" if supported else "tab:red"
            ax.axvspan(onset / 1000, (onset + duration) / 1000,
                       color=colour, alpha=.12)
            ax.axvline(onset / 1000, color=colour, lw=.8)
            if ax is axes[0] and limits[0] <= onset <= limits[1]:
                ax.text(onset / 1000, .98, check["stage"],
                        transform=ax.get_xaxis_transform(), va="top")
        ax.set_xlim(np.asarray(limits) / 1000)
    axes[-1].set_xlabel("Time after first DAT event (ms)")
    fig.suptitle("Raw PSEELoader counts; green=supported, red=unsupported model windows\n"
                 "Shading is the pipeline timing hypothesis, not measured LED commands")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, required=True)
    parser.add_argument("--saved-run", type=Path, required=True,
                        help="Baseline run with metadata and per-stage timing checks")
    parser.add_argument("--toolbox", type=Path,
                        default=ROOT.parent / "prophesee-automotive-dataset-toolbox")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bin-us", type=int, default=50)
    parser.add_argument("--context-us", type=int, default=1_000_000)
    parser.add_argument("--rerun-detector", action="store_true",
                        help="Also scan the full DAT with the current unchanged detector")
    args = parser.parse_args()
    if args.bin_us <= 0 or 500 % args.bin_us or args.context_us < 200_000:
        parser.error("bin-us must be a positive divisor of 500; context-us must be at least 200000")
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    metadata = json.loads((args.saved_run / "analysis_metadata.json").read_text())
    saved = metadata["timing_detection"]
    # Refuse accidentally comparing two different recordings. Also check its header below.
    if Path(metadata["data_file"]).name != args.dat.name:
        raise ValueError("Saved run names a different DAT recording")
    header = read_dat_header(args.dat)
    timing_fields = TimingConfig.__dataclass_fields__
    settings = {k: v for k, v in saved.items() if k in timing_fields}
    timing = TimingConfig(**settings)
    with (args.saved_run / "automatic_timing_check.csv").open(encoding="utf-8-sig") as f:
        checks = list(csv.DictReader(f))
    if len(checks) != len(timing.flash_colours):
        raise ValueError("Saved checks do not match the configured stage count")
    onsets = np.array([int(c["onset_after_read_us"]) for c in checks])
    onsets += int(metadata["actual_read_start_us"])
    start = max(0, int(onsets[0]) - 50_000) // args.bin_us * args.bin_us
    end = ((int(onsets[-1]) + timing.flash_period_us + args.context_us
            + args.bin_us - 1) // args.bin_us * args.bin_us)
    PSEELoader = load_psee(args.toolbox)
    loader = PSEELoader(str(args.dat.resolve()))
    last = int(loader.total_time()) - header.file_first_timestamp
    if end > last:
        end = (last + 1) // args.bin_us * args.bin_us
    if end < onsets[-1] + timing.flash_period_us:
        raise ValueError("Recording does not cover the saved sequence")
    print(f"Independent PSEELoader scan: {start}–{end} µs", flush=True)
    counts, maps, invalid = raw_scan(
        loader, header.file_first_timestamp, start, end, args.bin_us,
        onsets, timing.response_window_us)
    # Exact independent-decoder cross-check, with the SAME bin edges and time origin.
    position, _, _ = find_file_position_at_timestamp(
        args.dat, header.data_start, header.file_first_timestamp + start)
    other, _ = scan_polarity_bins(args.dat, position,
                                 header.file_first_timestamp + start,
                                 end - start, args.bin_us)
    if not np.array_equal(counts, other):
        raise ValueError("PSEELoader and project decoder disagree; inspect before timing analysis")
    np.savez_compressed(out / "raw_counts.npz", counts=counts, maps=maps,
                        start_us=start, bin_us=args.bin_us, onsets_us=onsets)
    write_csv(out / "raw_counts.csv", [dict(start_us=start + i * args.bin_us,
              OFF=int(c[0]), ON=int(c[1]), total=int(c.sum()))
              for i, c in enumerate(counts)])
    rows = []
    for i, c in enumerate(checks):
        rows.append(dict(stage=c["stage"], onset_after_file_first_us=int(onsets[i]),
                         raw_ON=int(maps[i, 1].sum()), raw_OFF=int(maps[i, 0].sum()),
                         active_pixels=int(np.any(maps[i] > 0, axis=0).sum()),
                         **{k: c[k] for k in ("ON_contrast_score", "OFF_edge_score", "supported")}))
    write_csv(out / "stage_comparison.csv", rows)
    plot_activity(out / "aligned_activity.png", counts, start, args.bin_us,
                  onsets, checks, timing.response_window_us,
                  [onsets[0] - 5000, onsets[-1] + timing.flash_period_us + 5000])
    plot_activity(out / "raw_context.png", counts, start, args.bin_us,
                  onsets, checks, timing.response_window_us, [start, end])
    for i, c in enumerate(checks):
        plot_activity(out / f"zoom_{c['stage']}.png", counts, start, args.bin_us,
                      onsets, checks, timing.response_window_us,
                      [onsets[i] - 1000, onsets[i] + timing.flash_period_us + 1000])
    fig, axes = plt.subplots(len(checks), 2, figsize=(9, 2.4 * len(checks)),
                             squeeze=False, constrained_layout=True)
    vmax = max(1, float(np.percentile(np.log1p(maps[maps > 0]), 99))) if maps.any() else 1
    for i, c in enumerate(checks):
        for p, name in enumerate(["OFF", "ON"]):
            im = axes[i, p].imshow(np.log1p(maps[i, p]), vmin=0, vmax=vmax,
                                    cmap="magma", origin="upper")
            axes[i, p].set_title(f"{c['stage']} {name}: {maps[i, p].sum():,} events")
    fig.colorbar(im, ax=axes, label="log(1 + events/pixel), shared scale")
    fig.savefig(out / "spatial_maps.png", dpi=120)
    plt.close(fig)
    # Use 500 µs envelopes so fine spike phase does not dominate recurrence.
    factor = 500 // args.bin_us
    envelope = counts[:len(counts) // factor * factor].reshape(-1, factor, 2).sum(axis=1)
    lags = np.arange(5000, min(200_000, (end - start) // 3) + 1, 500)
    recurrence = [dict(lag_us=int(lag), correlation=correlation(envelope, int(lag // 500)))
                  for lag in lags]
    write_csv(out / "recurrence.csv", recurrence)
    valid = [r for r in recurrence if r["correlation"] is not None]
    best = max(valid, key=lambda r: r["correlation"]) if valid else None
    cycle = 3 * timing.flash_period_us + timing.cycle_extra_delay_us
    cycle_lag = round(cycle / 500)
    cycle_corr = correlation(envelope, cycle_lag) if 0 < cycle_lag < len(envelope) else None
    result = dict(data_file=str(args.dat.resolve()), file_size_bytes=args.dat.stat().st_size,
                  first_DAT_timestamp_us=header.file_first_timestamp,
                  time_origin="first DAT event", interval_us=[start, end],
                  bin_us=args.bin_us, independent_decoder_counts_identical=True,
                  invalid_spatial_events=invalid, raw_events=int(counts.sum()),
                  saved_run=str(args.saved_run), timing=asdict(timing),
                  strongest_searched_recurrence=best, configured_RGB_cycle_us=cycle,
                  tested_cycle_lag_us=cycle_lag * 500, configured_cycle_correlation=cycle_corr,
                  stage_comparison=rows)
    source_paths = [ROOT / "src/flash_detection.py", ROOT / "src/temporal_alignment.py",
                    ROOT / "src/dat_decoder.py", Path(__file__),
                    args.toolbox / "src/io/psee_loader.py", args.toolbox / "src/io/dat_events_tools.py"]
    result["source_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    result["git_revision"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (out / "source_diff.patch").write_text(subprocess.check_output(
        ["git", "diff", "--", "src", "run_pipeline.py"], cwd=ROOT, text=True))
    if args.rerun_detector:
        print("Rerunning unchanged detector across retained recording", flush=True)
        pos, actual, _ = find_file_position_at_timestamp(
            args.dat, header.data_start,
            header.file_first_timestamp + int(metadata["actual_read_start_us"]))
        actual_start = actual - header.file_first_timestamp
        try:
            detection = detect_flash_onsets_chunked(args.dat, pos, actual,
                          actual_start, out / "pipeline", timing, FlashSearchConfig())
            result["detector_rerun"] = detection.details
            result["rerun_onsets_after_file_first_us"] = (detection.onsets_us + actual_start).tolist()
            result["rerun_matches_saved_onsets"] = bool(np.array_equal(
                detection.onsets_us + actual_start, onsets))
        except TimingDetectionError as error:
            result["detector_rerun"] = dict(error= str(error), diagnostics=error.diagnostics)
    (out / "evidence.json").write_text(json.dumps(result, indent=2))
    report = ["# Experiment 1: independent raw-event comparison", "",
              f"Recording: `{args.dat.name}`; interval {start}–{end} µs after first event.",
              f"PSEELoader and the project decoder agree in every {args.bin_us} µs ON/OFF bin.",
              "", "The coloured windows are the saved pipeline hypothesis. LED command times and RGB identity have not been independently measured.",
              "", "| Stage | Raw ON | Raw OFF | ON score | OFF score | Supported |",
              "|---|---:|---:|---:|---:|---|"]
    report += [f"| {r['stage']} | {r['raw_ON']} | {r['raw_OFF']} | {float(r['ON_contrast_score']):.3f} | {float(r['OFF_edge_score']):.3f} | {r['supported']} |" for r in rows]
    report += ["", f"Configured RGB cycle: {cycle} µs; envelope correlation at {cycle_lag * 500} µs: {cycle_corr}.",
               f"Strongest searched recurrence (500 µs resolution): {best}.",
               "", "Support is an OR of the ON-contrast and OFF-edge tests. A strong raw response can fail when the assumed dark reference also contains activity. A supported window need not have a strong ON response.",
               "", "Recurrence is event evidence, not a measurement of a particular colour or LED edge. Harmonics, scene changes and controller timing can affect it. No replacement RGB schedule or improved colour accuracy is claimed.",
               "", "![Aligned activity](aligned_activity.png)",
               "", "![Longer context](raw_context.png)",
               "", "Spatial maps use the hypothesised response windows and share one log colour scale; raw spatial counts are in raw_counts.npz."]
    if args.rerun_detector:
        report += ["", f"Unchanged detector reproduced the saved onsets exactly: {result.get('rerun_matches_saved_onsets', False)}.",
                   "Its detailed scores and block decisions are under `pipeline/`."]
    (out / "REPORT.md").write_text("\n".join(report) + "\n")
    print(json.dumps({k: result[k] for k in ["raw_events", "strongest_searched_recurrence",
          "configured_cycle_correlation"]}, indent=2), flush=True)
    print(f"Results: {out}", flush=True)


if __name__ == "__main__":
    main()
