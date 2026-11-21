"""Align a regular T1/T2/T3 recording to its firmware schedule and check event timing.

With --roi, also run Yang's response extraction on the programmed ON windows.
All camera times in the diagnostic are relative to the first DAT event.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import re
import shlex

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

import run_pipeline as yang
from dat_decoder import DisplayEventReader
from temporal_alignment import TimingDetectionError
from tools.prepare_recording_session import design_hash, load_design, rows_for_run


BIN_US = 100
LED_COLOURS = {"R": "#b73537", "G": "#23844d", "B": "#285fbb"}


def recording_schedule(path):
    match = re.fullmatch(r"(?P<sample>[a-z]+(?:_[a-z]+)*)_(?P<profile>T[123])_(?P<date>\d{8})\.dat",
                         path.name)
    if match is None:
        raise ValueError("Expected <colour>_T1/T2/T3_<YYYYMMDD>.dat.")
    _, profile, date = match.groups()
    design = load_design()
    if datetime.strptime(date, "%Y%m%d").date().isoformat() != design["session_id"]:
        raise ValueError("Recording date does not match the firmware session design.")
    run = next(run for run in design["runs"] if run["id"] == profile)
    schedule = rows_for_run(design, run, None)
    # Keep the binning exact and label LED colours from the firmware order.
    phases = {}
    for phase in ("preamble", "measurement"):
        phases[phase] = np.array([row[4:] for row in schedule if row[0] == phase])
        if np.any(phases[phase] % BIN_US):
            raise ValueError("Firmware targets need to fall on the diagnostic bin grid.")
    colours = [row[2] for row in schedule if row[0] == "measurement"]
    if colours != list("RGB") * (len(colours) // 3):
        raise ValueError("This diagnostic requires complete programmed RGB cycles.")
    return profile, design_hash(design), phases


def align_preamble(counts, marker):
    """Fit one translation by looking for the six expected polarity rises."""
    radius = 1000 // BIN_US
    prefix = np.vstack((np.zeros((1, 2), dtype=np.int64), np.cumsum(counts, axis=0)))
    contrast = np.log1p(prefix[2 * radius:] - prefix[radius:-radius])
    contrast -= np.log1p(prefix[radius:-radius] - prefix[:-2 * radius])
    edges = marker[:, :2].ravel()
    offsets = (edges - edges[0]) // BIN_US
    candidates = np.arange(len(contrast) - offsets[-1])
    if not len(candidates):
        raise ValueError("Recording is too short to locate the complete preamble.")
    polarities = np.tile([1, 0], len(marker))
    per_edge = contrast[candidates[:, None] + offsets, polarities]
    # Each edge must have at least fourfold contrast in its matching polarity.
    valid = np.all(per_edge >= np.log(4), axis=1)
    if not np.any(valid):
        raise ValueError("No complete polarity-resolved RGB preamble found.")
    score = np.where(valid, per_edge.sum(axis=1), -np.inf)
    best = int(np.argmax(score))
    others = np.abs(candidates - best) > 2 * radius
    if np.any(score[others] >= score[best] - 1):
        raise ValueError("Multiple plausible RGB preambles found.")
    estimates = []
    for edge, polarity in zip(best + offsets, polarities):
        lo = max(0, edge - radius)
        hi = min(len(contrast), edge + radius + 1)
        estimates.append((lo + int(np.argmax(contrast[lo:hi, polarity])) + radius) * BIN_US)
    return (best + radius) * BIN_US - int(edges[0]), np.array(estimates)


def stage_statistics(counts, measurement, end_us):
    """Summarise events in each fixed slot without moving or filling windows."""
    rows = []
    for i, (on, off, end) in enumerate(measurement):
        coverage = "complete" if end <= end_us else "partial" if on < end_us else "absent"
        lit = counts[on // BIN_US:off // BIN_US]
        dark = counts[off // BIN_US:end // BIN_US]
        slot = counts[on // BIN_US:end // BIN_US]
        on_peak = int(np.argmax(slot[:, 1])) if len(slot) and slot[:, 1].any() else None
        off_peak = int(np.argmax(dark[:, 0])) if len(dark) and dark[:, 0].any() else None
        rows.append(dict(
            stage=i + 1, cycle=i // 3 + 1, led="RGB"[i % 3], coverage=coverage,
            target_on_us=int(on), target_off_us=int(off), slot_end_us=int(end),
            lit_ON=int(lit[:, 1].sum()) if len(lit) else None,
            lit_OFF=int(lit[:, 0].sum()) if len(lit) else None,
            dark_ON=int(dark[:, 1].sum()) if len(dark) else None,
            dark_OFF=int(dark[:, 0].sum()) if len(dark) else None,
            first_ms_after_off_OFF=int(dark[:1000 // BIN_US, 0].sum()) if len(dark) else None,
            slot_ON_peak_count=int(slot[on_peak, 1]) if on_peak is not None else None,
            slot_ON_peak_bin_after_target_on_us=on_peak * BIN_US if on_peak is not None else None,
            dark_OFF_peak_count=int(dark[off_peak, 0]) if off_peak is not None else None,
            dark_OFF_peak_bin_after_target_off_us=off_peak * BIN_US if off_peak is not None else None,
        ))
    return rows


def epoch_activity(counts, measurement, complete_cycles):
    """Measure where recurrent activity lands in the programmed cycle grid."""
    cycle_us = int(measurement[2, 2] - measurement[0, 0])
    n = min(5, complete_cycles // 3)
    epochs = []
    if not n:
        return epochs
    for name, start in (("Beginning", 0), ("Middle", (complete_cycles - n) // 2),
                        ("End", complete_cycles - n)):
        lo = int(measurement[start * 3, 0])
        hi = lo + n * cycle_us
        waveform = counts[lo // BIN_US:hi // BIN_US].reshape(n, -1, 2)
        typical = np.median(waveform, axis=0)
        epochs.append((name, start + 1, start + n, lo, hi,
                       int(np.argmax(typical[:, 1])) * BIN_US,
                       int(np.argmax(typical[:, 0])) * BIN_US))
    return epochs


def save_activity_plot(path, counts, panels, *, pulses=None, span=None,
                       observed_edges=(), title, bin_us=BIN_US):
    figure, axes = plt.subplots(len(panels), 1, figsize=(12, 2.65 * len(panels) + 0.9),
                               layout="constrained", squeeze=False)
    handles = [
        Line2D([], [], color="#24292e", label="Camera ON"),
        Line2D([], [], color="#a55a10", label="Camera OFF"),
    ]
    if pulses is not None:
        handles.extend([Patch(color="#777777", alpha=0.18, label="Commanded ON (RGB)"),
                        Line2D([], [], color="#666666", ls="--", label="Commanded falling edge")])
    if span is not None:
        handles.append(Patch(color="#446aac", alpha=0.16, label="Programmed measurement"))
    if len(observed_edges):
        handles.append(Line2D([], [], color="#7b4599", ls=":", label="Marker response estimate"))
    for axis, (label, lo, hi, polarities) in zip(axes[:, 0], panels):
        begin = max(0, lo // bin_us)
        end = min(len(counts), (hi + bin_us - 1) // bin_us)
        edges = np.arange(begin, end + 1) * bin_us / 1000
        for polarity in polarities:
            axis.stairs(counts[begin:end, polarity], edges, baseline=None, lw=0.8,
                        color=("#a55a10", "#24292e")[polarity])
        if span is not None:
            axis.axvspan(span[0] / 1000, span[1] / 1000, color="#446aac", alpha=0.16)
        if pulses is not None:
            for i, (on, off, _) in enumerate(pulses):
                if off < lo or on > hi:
                    continue
                led = "RGB"[i % 3]
                axis.axvspan(on / 1000, off / 1000, color=LED_COLOURS[led], alpha=0.18, lw=0)
                axis.axvline(off / 1000, color=LED_COLOURS[led], ls="--", lw=0.7)
                if lo <= on < hi:
                    axis.text(on / 1000, .96, led, transform=axis.get_xaxis_transform(),
                              color=LED_COLOURS[led], fontsize=8, va="top", clip_on=True)
        for edge in observed_edges:
            if lo <= edge < hi:
                axis.axvline(edge / 1000, color="#7b4599", ls=":", lw=1.0)
        axis.set(xlim=(lo / 1000, hi / 1000), ylim=(0, None),
                 yscale="symlog", ylabel=f"Events / {bin_us:g} µs", title=label)
        axis.grid(axis="y", alpha=0.2)
    figure.legend(handles=handles, ncol=3, fontsize=8, frameon=False, loc="outside lower center")
    axes[-1, 0].set_xlabel("Time after first DAT event (ms)")
    figure.suptitle(title)
    figure.savefig(path, dpi=150)
    plt.close(figure)


def write_timing_plots(out, counts, marker, measurement, observed_edges, epochs, title):
    duration = len(counts) * BIN_US
    factor = 50
    overview = np.pad(counts, ((0, -len(counts) % factor), (0, 0)))
    overview = overview.reshape(-1, factor, 2).sum(axis=1)
    span = (int(measurement[0, 0]), int(measurement[-1, 2]))
    save_activity_plot(out / "full_recording.png", overview, [
        ("Full DAT · 5 ms bins", 0, duration, (1, 0))],
        span=span, title=title, bin_us=factor * BIN_US)

    marker_lo = max(0, int(marker[0, 0]) - 15_000)
    marker_hi = int(marker[-1, 2]) + 15_000
    save_activity_plot(out / "preamble_alignment.png", counts, [
        ("RGB marker", marker_lo, marker_hi, (1, 0)),
        ("Settling and the approach to measurement", marker_hi - 20_000,
         min(duration, span[0] + 45_000), (1, 0))],
        pulses=np.vstack((marker, measurement)), span=span, observed_edges=observed_edges,
        title=title)

    for name, first, last, lo, hi, _, _ in epochs:
        # Leave one slot of context so drift and late responses remain visible.
        pad = int(measurement[0, 2] - measurement[0, 0])
        lo, hi = max(0, lo - pad), min(duration, hi + pad)
        save_activity_plot(out / f"train_{name.lower()}.png", counts, [
            ("ON activity", lo, hi, (1,)), ("OFF activity", lo, hi, (0,))],
            pulses=measurement, title=f"{title} · {name}, cycles {first}–{last}")


def run_yang_responses(path, out, header, measurement, cycles, rectangles):
    width, height = header.width, header.height
    polygons = {}
    for i, (x0, y0, x1, y1) in enumerate(rectangles, 1):
        if not (0 <= x0 < x1 < width and 0 <= y0 < y1 < height):
            raise ValueError("ROI coordinates must define an in-frame rectangle.")
        polygons[f"ROI_{i}"] = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                                         dtype=np.int32)
    masks, areas = yang.make_roi_masks(polygons, width, height)
    timing = replace(yang.TIMING, num_rgb_repeats=cycles,
                     fade_duration_us=int(measurement[0, 1] - measurement[0, 0]),
                     response_window_us=int(measurement[0, 1] - measurement[0, 0]),
                     dark_interval_us=int(measurement[0, 2] - measurement[0, 1]),
                     flash_period_us=int(measurement[0, 2] - measurement[0, 0]))
    first = header.file_first_timestamp
    start = int(measurement[0, 0])
    position, _, _ = yang.find_file_position_at_timestamp(path, header.data_start, first + start)
    with DisplayEventReader(path, position, width, height) as reader:
        reference_end = int(measurement[min(8, cycles * 3 - 1), 2])
        on, off, _ = reader.window_counts(first + start, first + reference_end)
    activity = np.log1p(on + off)
    level = max(1.0, float(np.percentile(activity, 99.8)))
    reference = (255 * np.clip(activity / level, 0, 1)).astype(np.uint8)
    response_output = out / "yang_firmware_windows"
    response_output.mkdir()
    yang.save_png(response_output / "roi_reference.png", reference)
    yang.save_effective_roi_mask_figure(reference, polygons, masks,
                                        response_output / "roi_effective_masks.png")
    counts = yang.count_roi_flash_responses_chunked(
        path, position, first, 0, measurement[:cycles * 3, 0], masks, areas, width, height, timing)
    yang.save_roi_response_figure(reference, polygons, counts, response_output / "roi_response.png")
    brightness = yang.calculate_on_activity_brightness(
        counts, reference_roi=yang.BRIGHTNESS_REFERENCE_ROI,
        contrast_strength=yang.BRIGHTNESS_CONTRAST_STRENGTH,
        minimum_multiplier=yang.BRIGHTNESS_MIN_MULTIPLIER)
    colours, response_vectors, repeats = yang.build_roi_colours(counts, brightness, yang.COLOUR)
    yang.write_csv(response_output / "flash_responses.csv", counts)
    yang.write_csv(response_output / "diagnostic_response_vectors.csv",
                   yang.calculate_resulting_vectors(counts))
    yang.write_csv(response_output / "repeatability_summary.csv",
                   yang.calculate_repeatability_summary(counts))
    yang.write_csv(response_output / "normalised_colour_repeats.csv", repeats)
    yang.save_peak_summary_csv(response_output / "response_vectors.csv", response_vectors)
    yang.save_rgb_response_figure(response_vectors, response_output / "rgb_response.png")
    yang.create_pseudo_colour_gif(
        path, position, first, 0, start, width, height, polygons, masks, colours,
        response_output / "pseudo_colour_result.gif", replace(yang.VIDEO, gif_max_frames=30))
    return response_vectors


def run_baseline(path, out, header, measurement):
    baseline_out = out / "yang_original_detector"
    config = yang.TIMING
    try:
        detection = yang.detect_flash_onsets_chunked(
            path, header.data_start, header.file_first_timestamp, 0, baseline_out,
            config, yang.FLASH_SEARCH)
    except TimingDetectionError as error:
        rejected = error.diagnostics.get("rejected_best_candidate_after_read_us")
        summary = f"Yang's original {config.flash_period_us / 1000:g} ms stage model rejected the recording."
        if rejected is not None:
            summary += f" The best rejected candidate was at {rejected / 1000:.3f} ms."
        return summary
    yang.save_flash_figure(detection, 0, baseline_out, config)
    end = detection.onsets_us + config.fade_duration_us + config.peak_apply_time_us
    rows = [
        dict(stage=i + 1, led=config.flash_colours[i], yang_on_us=int(on),
             yang_off_us=int(off), firmware_on_us=int(target_on),
             firmware_off_us=int(target_off), yang_minus_firmware_on_us=int(on - target_on),
             yang_minus_firmware_off_us=int(off - target_off))
        for i, ((on, off), (target_on, target_off, _)) in enumerate(
            zip(zip(detection.onsets_us, end), measurement))
    ]
    yang.write_csv(baseline_out / "boundary_comparison.csv", rows)
    return (
        f"Yang's original {config.flash_period_us / 1000:g} ms stage model accepted "
        f"an R1 candidate at {detection.onsets_us[0] / 1000:.3f} ms "
        f"({detection.details['supported_flashes']}/{len(config.flash_colours)} supported). "
        "Compared by stage number, "
        f"its first and last rising boundaries differ from firmware by "
        f"{rows[0]['yang_minus_firmware_on_us'] / 1000:+.3f} and "
        f"{rows[-1]['yang_minus_firmware_on_us'] / 1000:+.3f} ms."
    )


def write_report(out, path, design_id, first, last, counts, phases, offset,
                 observed_edges, rows, epochs, baseline, vectors, rectangles, include_baseline):
    marker = phases["preamble"]
    train = phases["measurement"]
    on_us, off_us, slot_end_us = train[0]
    start_us = int(on_us + offset)
    cycles = len(train) // 3
    slot_us = int(slot_end_us - on_us)
    complete = [r for r in rows if r["coverage"] == "complete"]
    lit_on = sum(r["lit_ON"] for r in complete)
    dark_on = sum(r["dark_ON"] for r in complete)
    in_window = f"{lit_on / (lit_on + dark_on):.1%}" if lit_on + dark_on else "undefined"
    outside_max = sum(r["slot_ON_peak_bin_after_target_on_us"] >= off_us - on_us
                      for r in complete if r["slot_ON_peak_count"] is not None)
    pre_start = max(0, start_us - max(25_000, 3 * slot_us))
    pre_slots = counts[pre_start // BIN_US:start_us // BIN_US, 1]
    first_slots = counts[start_us // BIN_US:(start_us + 3 * slot_us) // BIN_US, 1]
    first_peak = rows[0]["slot_ON_peak_bin_after_target_on_us"]
    peak_sentence = (f"Its strongest ON bin starts {first_peak / 1000:.3f} ms after the target."
                     if first_peak is not None else "The slot has no ON peak.")
    edge_table = [
        f"| {'RGB'[i // 2]} {'ON' if i % 2 == 0 else 'OFF'} | "
        f"{(target + offset) / 1000:.3f} | {observed / 1000:.3f} | "
        f"{(observed - target - offset) / 1000:+.3f} |"
        for i, (target, observed) in enumerate(zip(marker[:, :2].ravel(), observed_edges))
    ]
    epoch_table = []
    for name, a, b, _, _, on, off in epochs:
        section = rows[(a - 1) * 3:b * 3]
        section_lit = sum(r["lit_ON"] for r in section)
        section_dark = sum(r["dark_ON"] for r in section)
        fraction = f"{section_lit / (section_lit + section_dark):.2%}" if section_lit + section_dark else "—"
        epoch_table.append(f"| {name} | {a}–{b} | {on / 1000:.3f} | {off / 1000:.3f} | {fraction} |")
    report = [
        f"# Timing diagnostic for {path.stem}", "",
        f"Firmware design SHA-256 `{design_id}`. DAT coverage is {(last-first) / 1e6:.6f} s "
        f"with {counts.sum():,} events. Camera times below are relative to the first DAT event "
        f"(raw timestamp {first} µs).", "",
        "## Firmware and preamble", "",
        f"The firmware schedules {cycles} RGB cycles at {3 * slot_us / 1000:g} ms per cycle. "
        f"Each LED is ON for {(off_us - on_us) / 1000:g} ms and OFF for "
        f"{(slot_end_us - off_us) / 1000:g} ms before the next slot. "
        f"Measurement starts at controller time {on_us / 1e6:.3f} s and runs for "
        f"{(train[-1, 2] - on_us) / 1e6:.3f} s including the last dark gap.", "",
        f"The joint six-edge marker fit gives a single offset of {offset / 1e6:.6f} s. "
        f"This places the first measurement command at {start_us / 1e6:.6f} s in the DAT. "
        f"The preamble spans {(marker[-1, 2] - marker[0, 0]) / 1000:g} ms including blue's "
        f"final {(marker[-1, 2] - marker[-1, 1]) / 1000:g} ms gap, followed by "
        f"{(on_us - marker[-1, 2]) / 1000:g} ms settling. Omitting the final marker gap "
        f"would place the predicted start {(marker[-1, 2] - marker[-1, 1]) / 1000:g} ms early. "
        "The marker estimates locate polarity rises in 100 µs bins using local count contrast. "
        "The mapped times are firmware targets in the camera time coordinate. They carry marker "
        "response latency and any relative clock error.", "",
        "| Marker | Mapped target (ms) | Event rise estimate (ms) | Event minus target (ms) |",
        "|---|---:|---:|---:|", *edge_table, "",
        f"The {(start_us - pre_start) / 1000:g} ms immediately before the first command contain {pre_slots.sum():,} "
        f"ON events (peak {int(pre_slots.max(initial=0)):,} per 100 µs). The first programmed "
        f"cycle contains {first_slots.sum():,} (peak {int(first_slots.max(initial=0)):,}). "
        f"The first scheduled slot contains {rows[0]['lit_ON']:,} ON events during ON time and "
        f"{rows[0]['dark_ON']:,} in the gap. {peak_sentence}", "",
        "## Complete-train comparison", "",
        f"The DAT time range covers {len(complete)}/{len(rows)} complete programmed slots. Across those slots, "
        f"{in_window} of ON events occur inside the programmed ON intervals. "
        f"The highest ON bin lands after the programmed falling edge in {outside_max} slots. "
        "The stage CSV includes clipped coverage and counts before and after each mapped falling "
        "edge. Its peak offsets describe activity found within each slot. A peak can arise from "
        "adjacent flashes or response tails.", "",
        "The peaks below are the dominant bins of the median cycle waveform within each sampled "
        "section, measured from the programmed cycle start. The plotted rising and falling targets "
        "allow direct comparison to the ON and OFF traces.", "",
        "| Section | Cycles | Dominant ON phase (ms) | Dominant OFF phase (ms) | ON events inside ON windows |",
        "|---|---:|---:|---:|---:|", *epoch_table, "",
        f"End minus beginning dominant ON phase is {(epochs[-1][-2] - epochs[0][-2]) / 1000:+.3f} ms "
        "on this cycle grid. OFF activity forms broad tails that span slot boundaries in the "
        "zoom plots. Brightness changes, event response latency and clock-rate mismatch can "
        "all affect these phase statistics.", "",
        "## Yang baseline and ROI extraction", "", baseline, "",
        "Yang's detector needs the correct slot duration and a measurement-phase anchor for regular "
        "T profiles. The original three-repeat automatic check cannot assess alignment across the take. "
        "The existing ROI counter and ON_PEAK extraction accept the supplied fixed RGB windows. "
        "Use the vectors for diagnostics. Verify the clock mapping and response-window coverage "
        "before interpreting them as channel measurements.", "",
    ]
    if vectors:
        report.extend(["The diagnostic run used these image-space rectangles, in sensor pixels. "
                       "Check the sample identity on the ROI overlay before interpreting its vector.", ""])
        for rectangle, row in zip(rectangles, vectors):
            rgb = ", ".join(f"{row[f'vector_{led}']:.3f}" for led in "RGB")
            report.append(f"- {row['roi']} {tuple(rectangle)} yielded ON_PEAK (R, G, B) = ({rgb}).")
        report.extend(["", "These are relative event-response vectors from the supplied windows. "
                       "The GIF uses Yang's display mapping.", ""])
    invocation = ["python3", "run_firmware_diagnostic.py", "--dat", str(path),
                  "--output-root", str(out.parent)]
    for rectangle in rectangles or []:
        invocation.extend(["--roi", *map(str, rectangle)])
    if include_baseline:
        invocation.append("--baseline")
    report.extend(["## Reproduce", "", "Run from the repository root with its Python requirements installed. "
                   "Choose a fresh output root to retain an existing run.", "",
                   "```sh", shlex.join(invocation), "```", ""])
    (out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("diagnostics"))
    parser.add_argument("--roi", nargs=4, type=int, action="append", metavar=("X0", "Y0", "X1", "Y1"),
                        help="Optional rectangle in sensor pixels. Repeat for additional ROIs.")
    parser.add_argument("--baseline", action="store_true", help="Run the original automatic detector.")
    args = parser.parse_args()
    path = args.dat.resolve()
    out = args.output_root / path.stem
    if out.exists():
        parser.error(f"Output directory already exists: {out}")
    profile, design_id, phases = recording_schedule(path)
    header = yang.read_dat_header(path)
    if not header.width or not header.height:
        raise ValueError("DAT header is missing its sensor dimensions.")
    with DisplayEventReader(path, header.data_start, header.width, header.height) as reader:
        last = reader.last_timestamp
    first = header.file_first_timestamp
    duration = last - first + 1
    print(f"Scanning {path.name} in {BIN_US} µs bins", flush=True)
    counts, _ = yang.scan_polarity_bins(path, header.data_start, first, duration, BIN_US)
    expected_events = (path.stat().st_size - header.data_start) // header.event_size
    if counts.sum() != expected_events:
        raise ValueError("Binned event count differs from the DAT record count.")
    offset, observed_edges = align_preamble(counts, phases["preamble"])
    marker = phases["preamble"] + offset
    train = phases["measurement"] + offset
    rows = stage_statistics(counts, train, duration)
    cycles = sum(r["coverage"] == "complete" for r in rows) // 3
    if cycles < 3:
        raise ValueError("Fewer than three complete measurement cycles follow the marker.")
    epochs = epoch_activity(counts, train, cycles)
    out.mkdir(parents=True, exist_ok=False)
    print(f"Applying marker offset {offset} µs to {profile}; {cycles} complete cycles in the DAT",
          flush=True)
    write_timing_plots(out, counts, marker, train, observed_edges, epochs, path.stem)
    yang.write_csv(out / "stage_statistics.csv", rows)
    vectors = run_yang_responses(path, out, header, train, cycles, args.roi) if args.roi else []
    baseline = run_baseline(path, out, header, train) if args.baseline else "Baseline was skipped."
    write_report(out, path, design_id, first, last, counts, phases, offset, observed_edges,
                 rows, epochs, baseline, vectors, args.roi, args.baseline)
    print(f"Saved {out / 'REPORT.md'}")


if __name__ == "__main__":
    main()
