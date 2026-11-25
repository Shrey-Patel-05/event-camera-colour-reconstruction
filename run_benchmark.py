"""Evaluate Yan's RGB reconstruction on the 16 November Valspar batch recordings."""

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
from dataclasses import asdict, replace
from datetime import datetime
import json
from itertools import combinations
from pathlib import Path

import numpy as np

import run_pipeline as yan
from temporal_alignment import TimingDetectionError
from swatch_rois import load_layout, save_layout
from tools.prepare_recording_session import load_design

ROOT = Path(__file__).resolve().parent
REFERENCES = {
    "black": ("W36c", (63, 62, 62)), "grey": ("R76D", (159, 148, 141)),
    "light_blue": ("R145B", (72, 131, 188)), "dark_green": ("W39d", (0, 110, 72)),
    "yellow": ("X68R139F", (220, 164, 6)), "orange": ("W24D", (218, 111, 44)),
    "purple": ("X26R61F", (102, 70, 116)), "red": ("L6cW11d", (182, 58, 63)),
}


def classify(path, design):
    batch = path.parent.name.lower()
    stem = path.stem.lower()
    prefix = batch + "_"
    if not stem.startswith(prefix):
        raise ValueError("Unidentified recording and firmware profile")
    parts = stem[len(prefix):].upper().split("_")
    if len(parts) not in (2, 3) or parts[-1] != design["session_id"].replace("-", ""):
        raise ValueError("Unknown recording name or session")
    run = next((r for r in design["runs"] if r["id"] == parts[0]), None)
    if not run:
        raise ValueError("Unknown session run")
    if run["mode"] in ("off", "single", "irregular"):
        raise ValueError({"off": "LEDs off", "single": "Single LED",
                          "irregular": "Shuffled RGB with omitted pulses"}[run["mode"]])
    profile = parts[1] if len(parts) == 3 else run.get("profile")
    if run["mode"] == "selected" and profile not in ("T1", "T2", "T3"):
        raise ValueError("Missing selected timing profile")
    if run["mode"] != "selected" and len(parts) != 2:
        raise ValueError("Unexpected timing profile suffix")
    return run, profile


def layout_path(directory, path, run):
    name = path.parent.name.lower()
    if run["layout"] != "A":
        name += "_" + run["layout"]
    return directory / (name + ".json")


def draw_layout(path, directory, swatches):
    run, _ = classify(path, load_design())
    labels = swatches or [path.parent.name.lower()]
    if any(label not in REFERENCES for label in labels):
        raise ValueError("Specify one or more Valspar names with --swatches.")
    header = yan.read_dat_header(path)
    # A time near the median event is generally in the active train, even after a long dark lead-in.
    count = (path.stat().st_size - header.data_start) // header.event_size
    with path.open("rb") as stream:
        stream.seek(header.data_start + count // 2 * header.event_size)
        middle = int.from_bytes(stream.read(4), "little") - header.file_first_timestamp
    frame, _, _ = yan.select_clear_reference_frame(
        path, header.data_start, header.file_first_timestamp, 0, header.width, header.height,
        first_onset_us=max(0, middle - yan.ROI.reference_search_duration_us // 2),
        config=replace(yan.ROI, reference_clip_value=16, reference_start_after_read_us=None,
                       automatic_reference_frame=False))
    definitions = [(f"ROI_{i}", f"Select {label}", (255, 255, 255))
                   for i, label in enumerate(labels, 1)]
    polygons = yan.choose_polygon_rois(frame, definitions, yan.ROI.display_scale)
    output = layout_path(directory, path, run)
    save_layout(output, path.parent.name, path.name, header.width, header.height,
                polygons, dict(zip(polygons, labels)))
    print(output)


def count_windows(path, h, onsets, timing, masks, areas):
    first = h.file_first_timestamp
    position, _, _ = yan.find_file_position_at_timestamp(path, h.data_start, first + int(onsets[0]))
    return yan.count_roi_flash_responses_chunked(
        path, position, first, 0, onsets, masks, areas, h.width, h.height,
        timing, chunk_events=yan.ROI.chunk_events)


def metrics(share, rgb, reference):
    ref = np.asarray(reference, dtype=float)
    ref_share = ref / ref.sum()
    bias = np.asarray(share) - ref_share
    difference = np.asarray(rgb) - ref
    row = dict(balance_loss=0.5 * np.abs(bias).sum(), rgb_mae=np.abs(difference).mean(),
               neutral_loss=0.5 * np.abs(1 / 3 - ref_share).sum())
    for j, c in enumerate("RGB"):
        row.update({f"share_{c}": share[j], f"bias_{c}_pp": bias[j] * 100,
                    f"rgb_{c}": rgb[j], f"error_{c}": difference[j]})
    return row


def csv_table(path, rows, columns):
    fields = list(dict.fromkeys(columns + [k for row in rows for k in row]))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def macro_mean(rows, field):
    """Average ROIs within take/swatch, then takes within swatch, then swatches."""
    by_swatch = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if field in row:
            by_swatch[row["swatch"]][row["recording"]].append(row[field])
    if by_swatch:
        return float(np.mean([np.mean([np.mean(v) for v in records.values()])
                              for records in by_swatch.values()]))


def repeatability(inventory, scores):
    """Compare separate CA captures sharing one batch layout, swatch, ROI and timing profile."""
    groups = defaultdict(list)
    for row in scores:
        take = inventory[row["recording"]]
        if take["run"] in ("CA1", "CA2", "CA3"):
            batch_path = Path(row["recording"]).parent.as_posix()
            key = (batch_path, row["profile"], row["swatch"], row["roi"], row["arm"])
            groups[key].append(row)

    result = []
    for (batch, profile, swatch, roi, arm), cases in sorted(groups.items()):
        valid = [row for row in cases if row["status"] == "ok"]
        distances = []
        for left, right in combinations(valid, 2):
            if inventory[left["recording"]]["run"] == inventory[right["recording"]]["run"]:
                continue
            distances.append(sum(abs(left["share_" + c] - right["share_" + c]) for c in "RGB") / 2)
        result.append(dict(batch=batch, profile=profile, swatch=swatch, roi=roi, arm=arm,
                           available_takes=len(cases), scored_takes=len(valid), pairs=len(distances),
                           mean_pair_distance=float(np.mean(distances)) if distances else None,
                           mean_target_loss=macro_mean(valid, "balance_loss")))
    return result


def save_swatch_figure(inventory, scores, out):
    from matplotlib import pyplot as plt
    from matplotlib.patches import Rectangle

    cells = defaultdict(list)
    conditions = set()
    display_rows = list(scores)
    represented = {row["recording"] for row in scores}
    for name, take in inventory.items():
        if take["status"] == "eligible" and name not in represented and take["batch"] in REFERENCES:
            display_rows.append(dict(recording=name, swatch=take["batch"], arm="A",
                                     status="rejected" if "labels" in take else "input_error"))
    for row in display_rows:
        take = inventory[row["recording"]]
        condition = take["run"]
        if condition != take["profile"] and take["profile"] != "legacy":
            condition += "/" + take["profile"]
        conditions.add(condition)
        cells[row["swatch"], condition].append(row)
    if not cells:
        return
    columns = ["Valspar"] + sorted(conditions, key=lambda c: (c[0] not in "LT", c))
    names = [name for name in REFERENCES if any(s == name for s, _ in cells)]
    fig, ax = plt.subplots(figsize=(1.6 * len(columns), 0.7 * len(names) + 1.5))
    for i, name in enumerate(names):
        for j, condition in enumerate(columns):
            cases = cells.get((name, condition), [])
            valid = [r for r in cases if r["status"] == "ok"]
            if j == 0:
                rgb = np.asarray(REFERENCES[name][1])
            elif valid:
                rgb = np.mean([[r["rgb_" + c] for c in "RGB"] for r in valid], axis=0)
            else:
                label = "Input error" if any(r["status"] == "input_error" for r in cases) else (
                    "Rejected" if cases else "No take")
                ax.text(j, i, label, ha="center", va="center", color="0.4", fontsize=9)
                continue
            ax.add_patch(Rectangle((j - 0.47, i - 0.41), 0.94, 0.82, facecolor=rgb / 255))
            unit = rgb / 255
            linear = np.where(unit <= 0.04045, unit / 12.92, ((unit + 0.055) / 1.055) ** 2.4)
            ink = "black" if np.dot(linear, [0.2126, 0.7152, 0.0722]) > 0.179 else "white"
            ax.text(j, i, " ".join(str(round(v)) for v in rgb), ha="center", va="center",
                    color=ink, fontsize=9)
    ax.set(xlim=(-0.5, len(columns) - 0.5), ylim=(len(names) - 0.5, -0.5),
           yticks=range(len(names)), yticklabels=[n.replace("_", " ").title() for n in names],
           xticks=range(len(columns)), xticklabels=columns)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, pad=6)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Valspar digital references and Yan display RGB by recording condition", pad=18)
    ax.set_xlabel("Numbers are 8-bit RGB, rounded for display. Cells average available estimates for the same swatch and condition.",
                  labelpad=10, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "yan_rgb.png", dpi=145)
    plt.close(fig)


def recording_timing(design, run, profile):
    """Change only the durations configured for Yan's fixed RGB detector."""
    if run["mode"] == "legacy":
        legacy = design["legacy_reconstruction"]
        on_us, off_us = legacy["ramp_us"], legacy["zero_command_us"]
        basis = "nominal legacy ramp plus zero interval; software overhead adds time"
    else:
        values = design["profiles"][profile]
        on_us, off_us = values["on_us"], values["off_us"]
        basis = "Arduino session profile"
    config = replace(
        yan.TIMING, fade_duration_us=on_us, peak_apply_time_us=0, dark_interval_us=off_us,
        flash_period_us=on_us + off_us, cycle_extra_delay_us=0,
        response_delay_us=0, response_window_us=on_us,
    )
    return config, basis


def extract(job):
    path, layout, out, run, profile = job
    out.mkdir(parents=True)
    timing, basis = recording_timing(load_design(), run, profile)
    result = dict(paths={}, errors={}, diagnostics={}, timing=asdict(timing), timing_basis=basis)
    header = yan.read_dat_header(path)
    polygons, labels = load_layout(layout, header.width, header.height)
    if not set(labels.values()) <= REFERENCES.keys():
        raise ValueError("Unknown Valspar swatch label")
    result["labels"] = labels
    definitions = [(key, label, (255, 255, 255)) for key, label in labels.items()]
    raw, _ = yan.make_roi_masks(polygons, header.width, header.height)
    masks, areas, _ = yan.prepare_analysis_roi_masks(raw, definitions, yan.ROI.nested_roi_mode)
    first = header.file_first_timestamp
    position, actual, _ = yan.find_file_position_at_timestamp(
        path, header.data_start, first + yan.SKIP_BEFORE_TIME_US)
    try:
        detection = yan.detect_flash_onsets_chunked(
            path, position, actual, actual - first, out / "yan", timing, yan.FLASH_SEARCH)
    except TimingDetectionError as error:
        result["errors"]["A"] = str(error)
        return result
    onsets = detection.onsets_us + actual - first
    rows = count_windows(path, header, onsets, timing, masks, areas)
    yan.write_csv(out / "flash_responses.csv", rows)
    result["paths"]["A"] = rows
    result["diagnostics"] = dict(
        first_window_us=rows[0]["window_start_us"],
        supported_flashes=detection.details.get("supported_flashes"),
    )
    try:
        brightness = yan.calculate_on_activity_brightness(
            rows, yan.BRIGHTNESS_REFERENCE_ROI, yan.BRIGHTNESS_CONTRAST_STRENGTH,
            yan.BRIGHTNESS_MIN_MULTIPLIER)
        _, vectors, repeats = yan.build_roi_colours(rows, brightness, yan.COLOUR)
        result["vectors"] = vectors
        yan.write_csv(out / "response_vectors.csv", vectors)
        yan.write_csv(out / "normalised_colour_repeats.csv", repeats)
    except ValueError as error:
        result["errors"]["A"] = str(error)
    return result


def extract_safely(job):
    timing, basis = recording_timing(load_design(), job[3], job[4])
    try:
        return extract(job)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return dict(paths={}, errors={"A": str(error)}, diagnostics={},
                    timing=asdict(timing), timing_basis=basis)


def collect(data, layouts, out, jobs):
    inventory, work = {}, []
    design = load_design()
    for path in sorted(data.rglob("*.dat")):
        name = path.relative_to(data).as_posix()
        info = inventory[name] = dict(batch=path.parent.name, bytes=path.stat().st_size)
        try:
            run, profile = classify(path, design)
        except ValueError as error:
            info.update(status="excluded", reason=str(error))
            continue
        info.update(status="eligible", run=run["id"], profile=profile or "legacy")
        layout = layout_path(layouts, path, run)
        work.append((path, layout, out / "recordings" / name[:-4], run, profile))
    if not inventory:
        raise ValueError(f"No DAT files found in {data}")
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for job, result in zip(work, pool.map(extract_safely, work)):
            inventory[job[0].relative_to(data).as_posix()].update(result)
            print(f"Processed {job[0].name}", flush=True)
    return inventory


def save_report(inventory, out, data):
    scores, recordings = [], []
    for name, info in inventory.items():
        row = dict(recording=name, status=info["status"], reason=info.get("reason", ""),
                   run=info.get("run"), profile=info.get("profile"))
        if info["status"] == "eligible":
            timing = info["timing"]
            row.update(on_us=timing["fade_duration_us"], dark_us=timing["dark_interval_us"],
                       stage_period_us=timing["flash_period_us"], timing_basis=info["timing_basis"],
                       **info["diagnostics"])
            if "labels" not in info:
                row.update(status="input_error", reason=info["errors"]["A"])
            elif "vectors" not in info:
                row.update(status="rejected", reason=info["errors"].get("A", "No response"))
            for vector in info.get("vectors", []):
                swatch = info["labels"][vector["roi"]]
                score = dict(recording=name, roi=vector["roi"], swatch=swatch, arm="A",
                             profile=info["profile"], status="rejected",
                             reason="Insufficient ON response", code=REFERENCES[swatch][0])
                score.update({"ref_" + c: v for c, v in zip("RGB", REFERENCES[swatch][1])})
                if vector["final_display_R"] is not None:
                    share = [vector["vector_" + c] for c in "RGB"]
                    rgb = [vector["final_display_" + c] for c in "RGB"]
                    score.update(metrics(share, rgb, REFERENCES[swatch][1]), status="ok", reason="")
                scores.append(score)
        recordings.append(row)
    valid = [r for r in scores if r["status"] == "ok"]
    summary = []
    for swatch in ["ALL"] + sorted(REFERENCES):
        cases = valid if swatch == "ALL" else [r for r in valid if r["swatch"] == swatch]
        expected = [r for r in recordings if r["status"] != "excluded"
                    and (swatch == "ALL" or inventory[r["recording"]]["batch"] == swatch)]
        item = dict(swatch=swatch, eligible_takes=len(expected),
                    scored_takes=len({r["recording"] for r in cases}))
        for field in ("balance_loss", "rgb_mae", "bias_R_pp", "bias_G_pp", "bias_B_pp",
                      "error_R", "error_G", "error_B", "neutral_loss"):
            item[field] = macro_mean(cases, field)
        summary.append(item)
    repeats = repeatability(inventory, scores)
    csv_table(out / "scores.csv", scores, ["recording", "roi", "swatch", "status", "reason"])
    csv_table(out / "recordings.csv", recordings, ["recording", "status", "reason", "profile"])
    csv_table(out / "summary.csv", summary, ["swatch", "scored_takes", "eligible_takes"])
    csv_table(out / "repeatability.csv", repeats, ["swatch", "profile", "scored_takes"])
    save_swatch_figure(inventory, scores, out)

    def fmt(value, digits=3):
        return "—" if value is None else f"{value:.{digits}f}"

    lines = ["YAN PIPELINE WITH RECORDING-SPECIFIC ARDUINO TIMING", str(data), "",
             "T1       1 ms ON + 0.5 ms dark    1.5 ms between stage starts",
             "T2/CA    1 ms ON + 5 ms dark      6 ms between stage starts",
             "T3       5 ms ON + 5 ms dark      10 ms between stage starts",
             "L2       0.5 ms ramp + 0.5 ms dark, nominal; software overhead adds time", "",
             "Yan's original automatic first-onset detector, three RGB cycles and ON_PEAK extraction.",
             "The integration window equals the configured ON/ramp duration.",
             "Each take's applied durations and detector outcome are in recordings.csv.", "",
             "Swatch         scored/eligible    balance loss    RGB MAE      R pp      G pp      B pp"]
    for r in summary:
        lines.append(f"{r['swatch']:<13}      {r['scored_takes']:>2}/{r['eligible_takes']:<3}"
                     f"              {fmt(r['balance_loss']):>6}     {fmt(r['rgb_mae'], 1):>6}"
                     + "".join(f"    {fmt(r['bias_' + c + '_pp'], 1):>6}" for c in "RGB"))
    counts = {status: sum(r["status"] == status for r in recordings)
              for status in ("excluded", "input_error", "rejected", "eligible")}
    lines += ["", f"{len(recordings)} DAT files; {counts['excluded']} excluded; "
              f"{counts['input_error']} input errors; {counts['rejected']} detector/extraction rejections.",
              "Excluded takes have dark, single-channel, irregular or unidentified protocols.", "",
              "Balance loss is channel-share error on a 0–1 scale, with 0 best.",
              "RGB MAE is mean absolute error per channel on a 0–255 scale.",
              "Signed share errors are prediction minus reference, in percentage points.",
              "Averages weight swatches equally, then recordings and ROIs within each swatch.",
              "References are the supplied nominal Valspar digital RGB values.", "",
              "yan_rgb.png        Predicted and reference RGB swatches",
              "scores.csv         Every successful or weak ROI estimate and its RGB errors",
              "summary.csv        Overall and per-swatch errors",
              "recordings.csv     Every input, applied timing and rejection reason",
              "repeatability.csv  Distances between independent CA captures"]
    (out / "report.txt").write_text("\n".join(lines) + "\n")
    return lines


def write_settings(out, data):
    files = [Path(__file__), ROOT / "run_pipeline.py",
             ROOT / "tools/prepare_recording_session.py", *sorted((ROOT / "src").glob("*.py"))]
    settings = dict(data_root=str(data), session_design=load_design(),
                    timing_rule="ON duration and dark gap from the recording's Arduino profile",
                    num_rgb_repeats=yan.TIMING.num_rgb_repeats, references=REFERENCES,
                    colour=asdict(yan.COLOUR),
                    source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in files})
    (out / "settings.json").write_text(json.dumps(settings, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path.home() / "Downloads/colours")
    parser.add_argument("--roi-dir", type=Path, default=ROOT / "experiments/benchmark_rois")
    parser.add_argument("--output", type=Path, help="New output directory")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--draw-rois", type=Path, metavar="DAT")
    parser.add_argument("--swatches", nargs="+", choices=REFERENCES)
    args = parser.parse_args()
    if args.draw_rois:
        draw_layout(args.draw_rois, args.roi_dir, args.swatches)
        return
    if args.swatches or args.jobs < 1:
        parser.error("--swatches requires --draw-rois; --jobs must be positive")
    if not args.data_root.is_dir():
        parser.error(f"Recording directory missing: {args.data_root}")
    out = args.output or ROOT / "benchmark_results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out.mkdir(parents=True, exist_ok=False)
    inventory = collect(args.data_root.resolve(), args.roi_dir, out, args.jobs)
    (out / "observations.json").write_text(json.dumps(inventory, indent=2))
    write_settings(out, args.data_root.resolve())
    print("\n".join(save_report(inventory, out, args.data_root.resolve())))
    print(f"Report saved to {out / 'report.txt'}")


if __name__ == "__main__":
    main()
