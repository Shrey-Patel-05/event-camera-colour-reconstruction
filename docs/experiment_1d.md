# Experiment 1D — consistency of the existing ball-ROI colour measurements

The analysis is in [the generated report](../diagnostics/experiment_1d_10ms/REPORT.md).
The selected primary ROI is **ROI_1**, the upper sector of the ball, as confirmed
by the user. The saved run has four separate sector polygons; all four are
analysed individually. They are not combined into a newly defined whole-ball ROI.

## Reproduction

From the repository root, choose a fresh output directory:

```bash
python3 run_roi_consistency.py \
  --dat data/10ms_4s.dat \
  --saved-run new_led_full_recording_results/10ms_4s/20261022_125050_727915 \
  --evidence diagnostics/experiment_1_10ms/evidence.json \
  --primary-roi ROI_1 \
  --output diagnostics/experiment_1d_10ms \
  --sensitivity
```

Omit `--sensitivity` to perform A–E only. The optional shift analysis runs after
the baseline measurements and plots, and after confirming substantial ON
variation. Its 50% CV gate is an explicit execution heuristic, not a scientific
acceptance criterion. No shift is selected as a corrected alignment. The script
is scoped to the existing 7/9 recording/phase; its observational snapshot times
are fixed and it checks that they fall inside the analysed interval.

The program reads saved geometry and timing rather than using the current
`run_pipeline.py` settings, which now point to the **1 ms** recording with no
skip. The saved 7/9 run used **10 ms** windows, **10.5 ms** adjacent-stage spacing,
a **31.5 ms** predicted RGB cycle, and an actual retained start of **4,500,004 µs**.
It selected t0=4,020,450 µs after that retained start, or **8,520,454 µs after the
first DAT event**. No 100 ms period is substituted.

The prior Experiment 1 detector rerun already verified the saved phase; 1D does
not rerun the global search. It verifies that the phase, nine predicted onsets,
DAT header and file size agree with that evidence. It reconstructs the effective
masks through the existing functions, checks the saved areas, and compares the
mask overlay with the saved image. The overlay differs at 1,162 pixels confined
to ROI text annotation regions; outside those regions it is identical. The
original binary masks were not exported, so the archived polygon coordinates,
area checks, overlay and count reproduction are the available checks on mask
identity. No geometry is selected or adjusted using the response results.

`count_roi_flash_responses_chunked` performs the quantitative recount. A seek to
the earliest required window avoids rereading discarded events while preserving
the original timestamp origin. Baseline counts/densities and repeatability match
the saved CSVs exactly; response-vector/display fields agree to floating-point
precision (largest absolute difference approximately 2.22e-16). An independently accumulated
50 µs histogram integrates back to every one of the same 36 ROI stage counts.

Tests and whitespace verification:

```bash
python3 -m unittest discover -s tests -v
git diff --check
```

Four tests pass. The new fixture exercises different seek and reference origins,
half-open window boundaries, equal-timestamp ON/OFF events, invalid coordinates,
mask membership and area division; a comparison check rejects altered saved
densities. The actual-data comparisons above provide the principal reproduction
evidence.

## Implementation audit (Task A)

| Question | Actual local implementation |
|---|---|
| Global phase detection | `src/flash_detection.py:detect_flash_onsets_chunked` scans a whole-sensor overview, then overlapping fine-search contexts with 10 µs polarity bins. It continues past failed contexts and accepts the first context yielding a candidate that passes `detect_first_flash_automatically`. |
| Candidate checks | `src/temporal_alignment.py:evaluate_fixed_timing` compares ON activity against an assumed late-dark rate and OFF activity against an assumed endpoint edge. Per-stage support is ON-score **or** OFF-score ≥2.5. Overall acceptance includes first-stage support, at least 6/9 support, sufficient support in first/last triplets, startup/sequence checks and an ambiguity-width test. These are event-derived heuristic scores. |
| Nine windows | `build_fixed_flash_onsets`: tj=t0+j×period+floor(j/3)×cycle_extra_delay. Positive sync offset moves t0 later. Counting uses [tj+response_delay, tj+response_delay+response_window), with exported times converted back to first-event-relative µs. Here both delays/offset are zero. |
| ROI selection | `run_pipeline.py` invokes `configure_rois`, `select_clear_reference_frame`, then `choose_polygon_rois` **after** temporal detection. The reference frame is display-only. |
| Mask rules | `make_roi_masks` rasterises native-coordinate polygons with `cv2.fillPoly`. `prepare_analysis_roi_masks` can remove strictly contained child masks. Here EXCLUDE_CONTAINED finds no nesting/overlap; effective areas are 188,526 / 74,275 / 85,760 / 58,167 pixels. |
| Counting and polarity | `count_roi_flash_responses_chunked` includes only events with valid sensor coordinates and true mask membership inside each half-open response window. It counts every event; it does not binarise pixels. ON=1, OFF=0; ON/OFF/total are retained. Outside events never directly enter that ROI's response count. |
| Density | Each count is divided by the fixed effective mask area, yielding events per effective ROI pixel per response window. Repeatability uses sample standard deviation (ddof=1) and CV=100×std/mean. |
| Channel aggregation | `src/colour_mapping.py:build_roi_colours` takes the maximum ON density across repetitions independently for R, G and B. OFF and global timing-support flags do not gate these maxima. |
| Normalisation | `normalized_vector` divides the three selected densities by their sum; zero total returns a zero vector. Brightness, maximum scaling and desaturation affect display only. |
| Existing alternatives | `run_duration_experiment.py:add_derived_measurements` and `calculate_response_summaries` supply ON_MEAN and ON_MEDIAN comparisons here. They are reused rather than reimplemented. `calculate_resulting_vectors` in roi_analysis also exports mean ON/OFF/TOTAL diagnostics; it is not the baseline colour estimator. |

## What the measurements show

For ROI_1, predicted R responses have ON counts **1 / 49,258 / 51,493**, predicted
G responses **65,401 / 1,914 / 30,725**, and predicted B responses
**367,267 / 2,949 / 0**. Their ON CVs are **86.66%, 97.27% and 171.14%**.
These are large differences within a nominally repeated sequence. Only three
predicted repetitions in one recording are measured; the CVs are descriptive,
not a confidence interval or an experimentally calibrated rejection threshold.

The baseline maxima come from **R3, G1 and B1**. The normalised ON_PEAK signature
is **[0.106355, 0.135081, 0.758564]**, even though B3 has no ON events and B2 is
far below B1. B1 supplies **99.20%** of the ON events assigned to predicted blue
across repetitions in this ROI. Its failure of a global timing test does not
remove it from colour estimation. B3 contributes no ON maximum; its **110,078
OFF events** are retained in the response CSV but omitted from ON_PEAK.

The separate ON_MEDIAN diagnostic gives **[0.593956, 0.370484, 0.035559]**. This
large estimator dependence demonstrates how much the maximum summary depends
on extreme measurements. It does not establish that the median is physically
correct. A frozen-phase diagnostic excluding only B1 lowers the ON_PEAK blue
component to **0.024607**; excluding B3 leaves the baseline vector unchanged.
These are influence checks, not a proposal to discard unsupported stages.

The per-repetition signatures also differ substantially:

| Predicted RGB triplet | Relative ON R | Relative ON G | Relative ON B |
|---|---:|---:|---:|
| 1 | 0.000002 | 0.151157 | 0.848841 |
| 2 | 0.910146 | 0.035365 | 0.054489 |
| 3 | 0.626298 | 0.373702 | 0.000000 |

The sector comparison matters: ROI_2 and ROI_3 select B2 for their blue maxima,
while ROI_1 and ROI_4 select B1. Thus global support alone cannot determine an
individual ROI's useful measurements. All four sectors show substantial
same-colour variation; ON CVs across the twelve ROI/channel combinations range
from **65.10% to 171.14%**. The maximum vector by itself hides this variation;
Yan's existing repeatability exports do expose it when inspected.

## Spatial and temporal observations (Task E)

The [aligned plot](../diagnostics/experiment_1d_10ms/global_vs_roi_activity.png)
covers 8.535–8.620 s with unsmoothed 50 µs bins and all four saved masks.
The [complete sequence](../diagnostics/experiment_1d_10ms/all_nine_activity.png)
also includes R1 and G1. Green/red shading denotes global statistical support,
with all labels explicitly predicted. Y scales are separate, so apparent line
height across rows is not an event-fraction comparison; exact membership
fractions are in `roi_global_fractions.csv`.

Strong global ON bursts do occur inside ROI_1, but their relative contributions
change. For example, ROI_1 contains **41.75%** of global B1 ON events and only
**0.77%** of global B2 ON events. The ROI occupies **20.46%** of sensor pixels;
these fractions describe spatial activity, not calibrated irradiance or a
contamination estimate. In the chosen [8.598565, 8.599065) s interval it contains
**4,862 of 37,983 ON events (12.80%)**.

The OFF bands are visible in independently accumulated raw-count spatial maps,
including within the upper ball polygon. In [8.604585, 8.605085) s ROI_1 contains
**6,337 of 71,346 OFF events (8.88%)**; in [8.607585, 8.608085) s it contains
**5,399 of 64,149 (8.42%)**. Over the full predicted B3 window it contains
**110,078 of 988,061 OFF events (11.14%)**. This establishes that some banded
activity intersects the ROI. It does not establish the cause of the bands.
OFF does not directly enter ON_PEAK, and outside activity can influence the
initial global phase rather than the later ROI count itself.

The ROI trace shows an ON-burst-to-OFF-dominant change near the visually reported
region. It does **not** validate 8.600835 s as an exact transition edge:

| Interval after first event | Global ON / OFF | ROI_1 ON / OFF |
|---|---:|---:|
| [8.599835, 8.600835) s | 9 / 76,028 | 4 / 1,775 |
| [8.600835, 8.601835) s | 3 / 145,085 | 3 / 3,661 |

Both intervals are already OFF-dominated. The preceding selected 500 µs interval
at 8.598565 s is strongly ON-dominated globally (37,983 ON versus 15 OFF).
The [transition zoom](../diagnostics/experiment_1d_10ms/transition_zoom.png) retains
the 50 µs bins. These are camera responses, not LED command timestamps. Chosen
500 µs snapshots cannot exactly reproduce player frames with an unspecified
integration duration, timestamp convention or relative-time display setting.

Strong ROI_1 ON responses are not consistently positioned within predicted
stages. Its largest integrated 1 ms slice occurs at **1–2 ms for R2 versus
6–7 ms for R3**, and **8–9 ms for G1 versus 0–1 ms for G3**. R1 contains only one
event and supplies no robust phase information. B1's centroid is **4.548 ms**,
B2's **7.234 ms**, and B3's is undefined. These centroids use 50 µs bin centres;
they are not fitted onsets. Log-ON profile correlations between nonconstant
same-colour repetitions range from **−0.429 to −0.052** for ROI_1. Unequal
amplitudes, motion, timing errors and optical/camera response differences can all
affect these observational comparisons; the experiment does not isolate a cause.

## Optional artificial shift sensitivity (Task F)

After A–E established large variation, all nine windows were shifted together by
−2, −1, −0.5, 0, +0.5, +1 and +2 ms. Mask geometry, window duration, stage
spacing and estimator definitions were held fixed. The original global support
labels were not recomputed for the shifted hypotheses. All windows fit the DAT.

For ROI_1, the ON_PEAK blue component ranges from **0.616816 to 0.758564** across
this sweep. At +2 ms the signature is **[0.126009, 0.257175, 0.616816]**, versus
baseline **[0.106355, 0.135081, 0.758564]**; the L1 vector change is **0.283496**.
Even ±0.5 ms gives L1 changes **0.080921** and **0.100455**. These are absolute
changes in normalised response components, not percentages of colour accuracy.
The report and CSVs include all shifts, individual responses and repeatability
statistics for all four ROIs. **No shift is selected as physically correct.**

## Conclusion and next experiment

The existing ROI extraction and aggregation reproduce their intended arithmetic.
The saved predicted labels/windows nevertheless produce poorly repeated ROI
responses, and the relative signature depends strongly on estimator choice and
artificial phase perturbation. Global oddities alone did not establish this;
the direct ROI recount does.

The next priority is **independent illumination timing measurement followed by
evaluation of temporal validation**: record Arduino command transitions and
photodiode output with a shared trigger or measured offset to camera time, and
include a known first-red reference. This distinguishes commanded transitions,
optical output and event response. Test any improved phase/model validation
against this reference while retaining the current detector as the baseline.
Do not select timing by colour appearance or by minimising variation on this
same sequence.

There is no demonstrated need to replace the ROI extraction implementation at
this stage. Compare measurement windows and aggregation methods once timing is
independently established. Repeat across recordings and illumination durations,
and use a calibrated colour reference to evaluate colour accuracy separately
from repeatability. Without that reference, actual LED timing and optical
waveforms, this experiment cannot identify the true RGB phase, assign a unique
hardware cause, or claim calibrated surface colour.

## Output inventory

| File | Purpose |
|---|---|
| `REPORT.md`, `evidence.json` | Generated tables, seven research answers, provenance and reproduction checks |
| `nine_stage_ROI_1.csv`, `nine_stage_responses.csv` | Primary nine-stage table and all four ROIs, including support labels |
| `flash_responses.csv`, `response_vectors.csv`, `repeatability_summary.csv` | Reproduced pipeline output schemas |
| `roi_geometry.json`, `effective_masks.npz`, `roi_effective_masks.png` | Saved geometry and reconstructed effective masks |
| `same_colour_repetitions.png`, `repetition_spread.csv` | All individual ON/OFF measurements, peak sources and spread |
| `per_repeat_vectors.csv`, `estimator_comparison.csv` | Per-triplet vectors and existing peak/mean/median diagnostics |
| `unsupported_window_influence.csv` | Frozen-phase influence checks for B1/B3 |
| `global_vs_roi_activity.png`, `all_nine_activity.png`, `activity_50us.*` | Aligned global and ROI histograms |
| `within_stage_ON_profiles.png`, `within_stage_phase.csv`, `within_stage_correlations.csv` | Locations and similarity of responses within predicted windows |
| `roi_global_fractions.csv`, `observed_interval_fractions.csv` | Direct spatial membership fractions |
| `observed_spatial_activity.png`, `transition_zoom.png`, `transition_window_counts.csv` | Band observations and transition context |
| `sensitivity_*.csv`, `timing_sensitivity.png` | Artificial phase-shift responses, vectors and repeatability |
