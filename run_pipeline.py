"""End-to-end runner for the refactored DVS colour-response project.

Use DATA_FILE or pass --dat. For recorded peak timing, also pass --peak-csv.

Dependencies:
    python -m pip install numpy opencv-python matplotlib pillow
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import json
import sys

import numpy as np

# Allow running directly from the repository root without installing a package.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from dat_decoder import (  # noqa: E402
    find_file_position_at_timestamp,
    print_dat_header,
    read_dat_header,
    scan_polarity_bins,
)
from temporal_alignment import TimingConfig, build_fixed_flash_onsets  # noqa: E402
from peak_windows import read_peak_windows  # noqa: E402
from flash_detection import (  # noqa: E402
    FlashDetectionResult,
    FlashSearchConfig,
    detect_flash_onsets_chunked,
    save_flash_figure,
    scan_full_recording_overview,
)
from roi_analysis import (  # noqa: E402
    ROIConfig,
    calculate_on_activity_brightness,
    calculate_repeatability_summary,
    calculate_resulting_vectors,
    choose_polygon_rois,
    configure_rois,
    count_roi_flash_responses_chunked,
    make_roi_masks,
    prepare_analysis_roi_masks,
    save_effective_roi_mask_figure,
    save_png,
    save_roi_response_figure,
    select_clear_reference_frame,
    write_csv,
)
from colour_mapping import (  # noqa: E402
    ColourConfig,
    VideoConfig,
    build_roi_colours,
    create_pseudo_colour_gif,
    save_peak_summary_csv,
    save_rgb_response_figure,
)


# -----------------------------------------------------------------------------
# Experiment settings
# -----------------------------------------------------------------------------
DATA_FILE = Path("data/1ms_2s.dat")
SKIP_BEFORE_TIME_US =   0
MANUAL_FIRST_ONSET_US = None  # After the first DAT event; None uses automatic detection.

# These values must match the actual recording setup.
FADE_DURATION_US = 1000
PEAK_APPLY_TIME_US = 0
DARK_INTERVAL_US = 500
END_DELAY_US = 0
MEASURED_FLASH_PERIOD_US = None

FLASH_PERIOD_US = (
    FADE_DURATION_US + PEAK_APPLY_TIME_US + DARK_INTERVAL_US
    if MEASURED_FLASH_PERIOD_US is None
    else int(MEASURED_FLASH_PERIOD_US)
)

TIMING = TimingConfig(
    num_rgb_repeats=3,
    fade_duration_us=FADE_DURATION_US,
    peak_apply_time_us=PEAK_APPLY_TIME_US,
    dark_interval_us=DARK_INTERVAL_US,
    flash_period_us=FLASH_PERIOD_US,
    cycle_extra_delay_us=END_DELAY_US,
    sync_offset_us=0,
    response_delay_us=0,
    response_window_us=FADE_DURATION_US,
    flash_detection_bin_us=max(1, min(10, FADE_DURATION_US // 20)),
    first_red_baseline_us=1_000,
    timing_min_flash_score=2.5,
    timing_min_sequence_score=5.0,
    timing_min_supported_fraction=2 / 3,
    timing_max_startup_score=3.0,
    timing_edge_guard_us=max(
        max(1, min(10, FADE_DURATION_US // 20)),
        min(50, DARK_INTERVAL_US // 5, FADE_DURATION_US // 5),
    ),
)

FLASH_SEARCH = FlashSearchConfig(
    first_red_search_duration_us=None,
    detection_block_duration_us=1_000_000,
    overview_bin_us=1_000,
    max_detection_bins=2_000_000,
    chunk_events=1_000_000,
)

ROI = ROIConfig(
    num_rois=None,
    nested_roi_mode="EXCLUDE_CONTAINED",
    reference_window_us=50_000,
    reference_step_us=10_000,
    reference_search_duration_us=300_000,
    reference_start_after_read_us=None,
    reference_clip_value=1,
    reference_display_mode="TOTAL",
    display_scale=1.5,
    event_point_size=1,
    automatic_reference_frame=False,
    chunk_events=1_000_000,
)

COLOUR = ColourConfig(
    minimum_colour_response_events=1.0,
    minimum_colour_response_density=1e-6,
    on_peak_display_brightness=200.0,
    display_desaturation_fraction=0.12,
)

VIDEO = VideoConfig(
    start_after_read_us=None,
    duration_us=500_000,
    frame_window_us=500,
    frame_step_us=500,
    persistence_us=20_000,
    display_mode="TOTAL",
    event_point_size=1,
    event_clip_value=1,
    show_events_outside_rois=True,
    background_event_brightness=0.25,
    colour_blend=1.0,
    off_event_brightness=0.20,
    on_event_brightness=1.00,
    draw_roi_outlines=False,
    gif_fps=15.0,
    gif_max_frames=90,
    gif_loop=0,
    chunk_events=1_000_000,
)

BRIGHTNESS_REFERENCE_ROI = "ROI_1"
BRIGHTNESS_CONTRAST_STRENGTH = 9.0
BRIGHTNESS_MIN_MULTIPLIER = 0.22


def save_peak_window_figure(data_file, data_start, file_first_timestamp, available_end_us,
                            windows, output_dir):
    """Plot supplied integration windows against measured ON and OFF activity."""
    import matplotlib.pyplot as plt

    bin_us = 50
    cycles = len(windows) // 3
    panel_cycles = min(3, cycles)
    starts = (0, (cycles - panel_cycles) // 2, cycles - panel_cycles)
    led_colours = {"R": "#cb4040", "G": "#299557", "B": "#3d72d5"}
    figure, axes = plt.subplots(3, 1, figsize=(12, 8), layout="constrained")
    for ax, label, first in zip(axes, ("Beginning", "Middle", "End"), starts):
        subset = windows[first * 3:(first + panel_cycles) * 3]
        left = max(0, subset[0]["window_start_us"] - 1000)
        right = min(available_end_us, subset[-1]["window_end_us"] + 1000)
        position, _, _ = find_file_position_at_timestamp(
            data_file, data_start, file_first_timestamp + left)
        counts, _ = scan_polarity_bins(
            data_file, position, file_first_timestamp + left, right - left, bin_us)
        edges = (left + np.arange(len(counts) + 1) * bin_us) / 1000
        ax.stairs(counts[:, 1], edges, baseline=None, color="#272727", lw=0.85, label="Camera ON")
        ax.stairs(counts[:, 0], edges, baseline=None, color="#ad661a", lw=0.75, label="Camera OFF")
        for row in subset:
            colour = led_colours[row["led"]]
            ax.axvspan(row["window_start_us"] / 1000, row["window_end_us"] / 1000,
                       color=colour, alpha=0.2)
            ax.axvline(row["peak_us"] / 1000, color=colour, lw=0.8, ls="--")
            ax.text(row["peak_us"] / 1000, .98, f"{row['led']}{row['cycle']}",
                    transform=ax.get_xaxis_transform(), ha="center", va="top",
                    color=colour, fontsize=8)
        ax.set(xlim=(left / 1000, right / 1000), ylim=(0, None), yscale="symlog",
               ylabel=f"Events / {bin_us} µs", title=label)
        ax.grid(axis="y", alpha=0.2)
    axes[0].legend(loc="lower right", fontsize=8)
    axes[-1].set_xlabel("Time after first DAT event (ms)")
    figure.suptitle("Peak-centred response windows using the shared G/B offset per cycle")
    figure.savefig(output_dir / "peak_alignment.png", dpi=150)
    plt.close(figure)


def main(data_file: Path | None = None, *, peak_csv: Path | None = None,
         peak_window_us: int = 500, num_rois: int | None = None) -> None:
    data_file = DATA_FILE if data_file is None else Path(data_file)
    if not data_file.is_file():
        raise FileNotFoundError(
            f"DAT file not found: {data_file}\nPass --dat or set DATA_FILE in run_pipeline.py."
        )

    windows = read_peak_windows(Path(peak_csv), peak_window_us) if peak_csv is not None else None
    output_dir = (
        ROOT
        / "new_led_full_recording_results"
        / data_file.stem
        / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    header = read_dat_header(data_file)
    print_dat_header(header)
    if header.width is None or header.height is None:
        raise ValueError("DAT header is missing Width/Height.")

    target = header.file_first_timestamp + int(SKIP_BEFORE_TIME_US)
    read_start_position, actual_start_timestamp, skipped_count = (
        find_file_position_at_timestamp(data_file, header.data_start, target)
    )
    actual_read_start_us = actual_start_timestamp - header.file_first_timestamp
    width, height = int(header.width), int(header.height)

    print(
        f"Read start: {actual_read_start_us} us after the first DAT event; "
        f"skipped {skipped_count:,} events."
    )
    print(
        "R1 identity comes from the experimental start order; the event stream "
        "alone does not identify an unknown first colour."
    )

    # 1. Load the recorded response windows, or use the original timing paths.
    timing = TIMING
    roi_config = ROI
    if windows is not None:
        available_end_us, recording_overview = scan_full_recording_overview(
            data_file, read_start_position, actual_start_timestamp,
            actual_read_start_us, output_dir, FLASH_SEARCH,
        )
        onsets = np.array([row["window_start_us"] for row in windows], dtype=np.int64)
        onsets -= actual_read_start_us
        if onsets[0] < 0 or windows[-1]["window_end_us"] > actual_read_start_us + available_end_us:
            raise ValueError("Peak CSV response windows fall outside the retained DAT recording.")
        # The existing counter treats these anchors as response-window starts.
        timing = replace(TIMING, num_rgb_repeats=len(windows) // 3,
                         response_delay_us=0, response_window_us=peak_window_us)
        roi_config = replace(ROI, reference_clip_value=16.0)
        timing_details = {
            "source": "peak_csv_shared_gb_median",
            "peak_csv": str(Path(peak_csv).resolve()),
            "num_rgb_repeats": timing.num_rgb_repeats,
            "response_window_us": peak_window_us,
            "anchor": "response window start; peak_us in peak_windows.csv is its centre",
            "csv_time_origin": "first DAT event",
            "phase_definition": "per-cycle median of the G and B peak-bin start offsets",
        }
        print(f"Loaded {len(windows)} peak-centred windows of {peak_window_us} µs "
              f"from {peak_csv}.", flush=True)
        write_csv(output_dir / "peak_windows.csv", windows)
        save_peak_window_figure(
            data_file, header.data_start, header.file_first_timestamp,
            actual_read_start_us + available_end_us, windows, output_dir)
    elif MANUAL_FIRST_ONSET_US is None:
        detection = detect_flash_onsets_chunked(
            data_file,
            read_start_position,
            actual_start_timestamp,
            actual_read_start_us,
            output_dir,
            TIMING,
            FLASH_SEARCH,
        )
    else:
        onsets = build_fixed_flash_onsets(
            int(MANUAL_FIRST_ONSET_US) - actual_read_start_us, TIMING
        )
        available_end_us, overview = scan_full_recording_overview(
            data_file, read_start_position, actual_start_timestamp,
            actual_read_start_us, output_dir, FLASH_SEARCH,
        )
        if onsets[0] < 0 or (
            onsets[-1] + TIMING.response_delay_us + TIMING.response_window_us
            > available_end_us
        ):
            raise ValueError("Manual RGB response windows fall outside the retained recording.")
        bin_us = TIMING.flash_detection_bin_us
        left = max(0, int(onsets[0]) - 2 * TIMING.flash_period_us) // bin_us * bin_us
        right = min(available_end_us, int(onsets[-1]) + TIMING.flash_period_us)
        position, _, _ = find_file_position_at_timestamp(
            data_file, read_start_position, actual_start_timestamp + left
        )
        counts, _ = scan_polarity_bins(
            data_file, position, actual_start_timestamp + left, right - left, bin_us
        )
        detection = FlashDetectionResult(
            onsets_us=onsets,
            centres_us=left + (np.arange(len(counts)) + 0.5) * bin_us,
            total_counts=counts.sum(axis=1),
            smoothed_on_counts=np.convolve(
                counts[:, 1].astype(float), [0.2, 0.6, 0.2], mode="same"
            ),
            polarity_counts=counts,
            details={
                "source": "manual_first_onset",
                "first_onset_after_sync_us": int(onsets[0]),
                "manual_first_onset_after_file_first_us": int(MANUAL_FIRST_ONSET_US),
            },
            recording_overview=overview,
        )
    if windows is None:
        save_flash_figure(detection, actual_read_start_us, output_dir, TIMING, show=False)
        onsets = detection.onsets_us
        timing_details = detection.details
        recording_overview = detection.recording_overview

    # 2. Select a display-only event reference and draw ROIs.
    roi_definitions = configure_rois(roi_config.num_rois if num_rois is None else num_rois)
    reference_gray, reference_start_us, reference_details = (
        select_clear_reference_frame(
            data_file,
            read_start_position,
            actual_start_timestamp,
            actual_read_start_us,
            width,
            height,
            first_onset_us=int(onsets[0]),
            config=roi_config,
        )
    )
    save_png(output_dir / "roi_reference.png", reference_gray)

    polygons = choose_polygon_rois(
        reference_gray,
        roi_definitions,
        display_scale=roi_config.display_scale,
    )
    raw_masks, raw_areas = make_roi_masks(polygons, width, height)
    roi_masks, roi_areas, region_details = prepare_analysis_roi_masks(
        raw_masks,
        roi_definitions,
        nested_roi_mode=roi_config.nested_roi_mode,
    )
    save_effective_roi_mask_figure(
        reference_gray,
        polygons,
        roi_masks,
        output_dir / "roi_effective_masks.png",
    )

    # 3. Quantitative ON/OFF response extraction from the fixed RGB windows.
    rows = count_roi_flash_responses_chunked(
        data_file,
        read_start_position,
        actual_start_timestamp,
        actual_read_start_us,
        onsets,
        roi_masks,
        roi_areas,
        width,
        height,
        timing,
        chunk_events=roi_config.chunk_events,
    )
    save_roi_response_figure(
        reference_gray,
        polygons,
        rows,
        output_dir / "roi_response.png",
    )

    diagnostic_vectors = calculate_resulting_vectors(rows)
    repeatability = calculate_repeatability_summary(rows)
    brightness = calculate_on_activity_brightness(
        rows,
        reference_roi=BRIGHTNESS_REFERENCE_ROI,
        contrast_strength=BRIGHTNESS_CONTRAST_STRENGTH,
        minimum_multiplier=BRIGHTNESS_MIN_MULTIPLIER,
    )

    # 4. ON_PEAK relative colour response and pseudo-colour mapping.
    roi_colours, peak_summaries, colour_diagnostics = build_roi_colours(
        rows,
        brightness,
        COLOUR,
    )
    save_rgb_response_figure(
        peak_summaries,
        output_dir / "rgb_response.png",
    )

    write_csv(output_dir / "flash_responses.csv", rows)
    write_csv(output_dir / "diagnostic_response_vectors.csv", diagnostic_vectors)
    write_csv(output_dir / "repeatability_summary.csv", repeatability)
    write_csv(output_dir / "normalised_colour_repeats.csv", colour_diagnostics)
    save_peak_summary_csv(output_dir / "response_vectors.csv", peak_summaries)

    create_pseudo_colour_gif(
        data_file,
        read_start_position,
        actual_start_timestamp,
        actual_read_start_us,
        first_onset_us=int(onsets[0]),
        width=width,
        height=height,
        polygons=polygons,
        roi_masks=roi_masks,
        roi_colours=roi_colours,
        output_path=output_dir / "pseudo_colour_result.gif",
        config=VIDEO,
    )

    metadata = {
        "data_file": str(data_file),
        "actual_read_start_us": int(actual_read_start_us),
        "timing_detection": timing_details,
        "recording_overview": recording_overview,
        "roi_reference": reference_details,
        "roi_reference_start_us": int(reference_start_us),
        "raw_roi_areas": raw_areas,
        "effective_roi_areas": roi_areas,
        "roi_region_details": region_details,
        "brightness_response": brightness,
        "polygons": {name: polygon.tolist() for name, polygon in polygons.items()},
        "interpretation": (
            "Colour is a relative ON_PEAK event-response vector. Material-contrast "
            "brightness is display-only, not calibrated RGB or absolute intensity."
        ),
    }
    (output_dir / "analysis_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nAnalysis complete: {output_dir}")
    print("Generated core GitHub figures:")
    print("  peak_alignment.png" if windows is not None else "  flash_detection.png")
    print("  roi_response.png")
    print("  rgb_response.png")
    print("  pseudo_colour_result.gif")
    if windows is not None:
        for summary in peak_summaries:
            rgb = ", ".join(f"{summary[f'vector_{led}']:.3f}" for led in "RGB")
            print(f"  {summary['roi']} relative ON_PEAK RGB = ({rgb})")


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", type=Path, help="Prophesee DAT recording")
    parser.add_argument("--peak-csv", type=Path,
                        help="stage_statistics.csv generated for this same DAT recording")
    parser.add_argument("--peak-window-us", type=int, default=500,
                        help="Even width of each peak-centred window in microseconds (default: 500)")
    parser.add_argument("--num-rois", type=int, help="Number of polygons to draw interactively")
    args = parser.parse_args()
    if args.num_rois is not None and args.num_rois < 1:
        parser.error("--num-rois must be positive.")
    if args.peak_csv is None and args.peak_window_us != 500:
        parser.error("--peak-window-us requires --peak-csv.")
    main(args.dat, peak_csv=args.peak_csv, peak_window_us=args.peak_window_us, num_rois=args.num_rois)


if __name__ == "__main__":
    try:
        cli()
    finally:
        # Safe cleanup after interactive OpenCV ROI windows.
        try:
            import cv2
            cv2.destroyAllWindows()
        except Exception:
            pass
