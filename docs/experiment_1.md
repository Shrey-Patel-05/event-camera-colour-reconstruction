# Experiment 1 — distinguish raw event behaviour from processing errors

The initial experiment compares one DAT file through two readers: Prophesee's
`PSEELoader` (the reader used by `play_dat.py`) and the existing reconstruction
pipeline. It keeps the detector unchanged. The diagnostic produces quantitative
50 µs OFF/ON/total counts, individual stage zooms, spatial count maps and a
comparison with the pipeline's fixed timing hypothesis. Every bin uses the same
origin: microseconds after the first DAT event. Intervals are half open.

The saved `10ms_4s/20261022_125050_727915` run is the available 7/9 case. Its
configured illumination duration is **10 ms**, with a 500 µs dark interval;
it is not the 1 ms experiment described in the suggested plan. The recording
names are not measurements of the controller timing.

Run from the repository root with the Prophesee toolbox in the sibling directory:

```bash
python3 run_raw_diagnostic.py \
  --dat data/10ms_4s.dat \
  --saved-run new_led_full_recording_results/10ms_4s/20261022_125050_727915 \
  --output diagnostics/experiment_1_10ms \
  --rerun-detector
```

Choose a fresh output directory for each run. `--toolbox` overrides the sibling
toolbox path. `--bin-us 100` provides a second resolution check. The script's
default raw interval begins 50 ms before the saved schedule and includes another
second after it, so independent recurrence can be compared with the timing model.
The raw analysis never uses the detector's smoothed counts. Decoder agreement is
checked for every polarity bin; spatial maps retain event multiplicity instead
of clipping each pixel to a binary display. Out-of-bounds pixels are reported.

`--rerun-detector` scans the retained recording with the current detector source,
using the saved run's timing parameters and read start. It saves the detector's
per-stage scores, block decisions, timestamp assignments and report under
`pipeline/`; `evidence.json` records whether its onsets match the saved baseline.
No interactive ROI selection or pseudo-colour reconstruction is needed. Source
hashes, Git revision and the existing source diff identify the implementation
actually used. This is a rerun of the available refactored pipeline; equivalence
to an unavailable older original implementation is not assumed.

Inspect `REPORT.md`, `aligned_activity.png`, `raw_context.png`, `zoom_B1.png`,
`zoom_B3.png`, and `spatial_maps.png`. The two unsupported windows and the seven
supported windows are both plotted. The shaded sequence is a model hypothesis,
not independently measured illumination. The independent envelope recurrence
search covers 5–200 ms (bounded further by available context), at 500 µs
resolution, and can contain harmonics. It does not recover RGB identity.

The detector finds one starting phase and generates subsequent windows from a
fixed period. Its “7/9” means seven model windows meet a statistical support
test, not that seven independent flash edges were found. A window passes when
either its ON-contrast score or OFF-edge score exceeds 2.5. Six supported
windows can satisfy the overall fraction threshold. In particular, a large raw
ON response can fail if the model's supposed late-dark interval also has high
ON activity. A window can pass on its OFF edge with very little ON activity.

The existing `diagnostics/temporal_sync/REPORT.md` is historical evidence. Its
claimed recurrence rejection and its referenced `diagnose_temporal_sync.py`
are absent from the current source tree. Use this reproducible experiment to
assess the current code; that report alone does not establish a present fix.

## Connect timing to the third-year colour project

First establish timing against an independent reference: controller source and
command timing, a trigger signal or photodiode trace, plus a known first-red
reference. Raw event peaks describe the camera response; their absence cannot
by itself establish that an LED did not illuminate. A recurring event envelope
does not uniquely identify which colour caused it.

Then compare the preserved baseline with a proposed synchronisation method on
the same recordings. Report onset error, missed/false detections, drift and
failure rate. A useful first improvement to investigate is rejecting inconsistent
timing models before assigning RGB. Its thresholds need validation across
recordings, including motion and correct timing, rather than fitting one case.

For colour extraction, reuse the same effective ROI masks and report response
vectors per cycle as well as their aggregate. Sweep the integration-window phase
around independently established timing and quantify how much the colour vector
changes. Compare ON-max (the current method), ON-median and ON/OFF features on
held-out recordings. Measure repeatability separately from colour accuracy;
accuracy needs a colour reference and illumination/sensor calibration. Avoid
choosing timing by making the reconstructed colour look right, which would make
the evaluation circular.

Useful deliverables are paired timing-error and colour-error results, sensitivity
to window phase and illumination duration, and an explicit failure analysis.
The immediate experiment supplies raw evidence for deciding which timing change
to implement next; it does not yet establish improved colour accuracy.

Verification:

```bash
python3 -m unittest discover -s tests -p 'test_raw_diagnostic.py' -v
```
