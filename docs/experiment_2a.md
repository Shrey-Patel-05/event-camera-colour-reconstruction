# Experiment 2A — compare the other recordings

**The reliability problems are not specific to the saved 10 ms case.** The
unchanged 1 ms detector accepts a sequence with only **one ROI ON event**; the
100 ms sequence has substantially different same-colour repetitions and event
recurrence inconsistent with interpreting its configured RGB cycle as a verified
repetition period. These observations do not prove a shared hardware cause or
establish a corrected LED schedule.

The comparison uses the existing ROI counter, repeatability calculation, ON_PEAK
mapping and mean/median estimators. No detector, timing period or colour-mapping
algorithm was changed. All stage colours below are **predicted**.

Start with the [generated tables/report](../diagnostics/experiment_2a/REPORT.md),
[comparison CSV](../diagnostics/experiment_2a/comparison.csv), and
[repeatability figure](../diagnostics/experiment_2a/repeatability_and_estimators.png).

## Common spatial measurement and saved-run provenance

The saved 1 ms run has ROI reference/mask images but no coordinates, metadata or
response CSVs. Its ROI_1 image actually marks part of the **right sector**; its
upper-sector patch is labelled ROI_2. Therefore matching ROI names across old
outputs would not establish matching material regions.

This experiment instead reuses one archived polygon, unchanged, across all three
recordings: the **169,996-pixel upper-ball polygon** from the 100 ms run, named
`COMMON_UPPER` in the new outputs. Its placement on each saved reference was
visually inspected in [the comparison overlay](../diagnostics/experiment_2a/common_roi_comparison.png).
The polygon follows the same upper sector in those images. This is a spatial
control, not measured registration throughout each recording; motion and boundary
placement remain limitations.

COMMON_UPPER differs from Experiment 1D's 188,526-pixel ROI_1. For an equal-mask
comparison, 10 ms measurements were recounted with COMMON_UPPER. The original
1D outputs and original ROI geometry remain unchanged. No claim is made to
reproduce the missing original 1 ms ROI measurements.

| Recording | Saved timing run | Retained start after first event | Selected t0 after first event | Configured fade / dark / RGB cycle |
|---|---|---:|---:|---|
| `1ms_2s.dat` | `1ms_2s/20261022_141535_799356` | 0 µs | 2,412,700 µs | 1 / 0.5 / 4.5 ms |
| `10ms_4s.dat` | `10ms_4s/20261022_125050_727915` | 4,500,004 µs | 8,520,454 µs | 10 / 0.5 / 31.5 ms |
| `100ms_10s.dat` | `example/20261021_174732_769337` | 0 µs | 10,806,040 µs | 100 / 0.5 / 301.5 ms |

The 100 ms archive names its input `data/example.dat`. Its 233,248,933 events,
21,949,751 µs event span, every archived 1 ms global OFF/ON bin, and the exact
native ROI stage counts agree with the current `100ms_10s.dat`. This supports
the association independently of the filename. Some other `example/` runs used
a 1 ms model on the same 100 ms recording; they were not used as a genuine
`1ms_2s.dat` baseline.

The 1 ms and 100 ms detectors were rerun unchanged, reproducing saved onsets and
all per-stage support scores. The 10 ms phase reuses the verified Experiment 1
rerun. Its original skip differs from the other searches, so this is a comparison
of available accepted cases, not a controlled causal test of duration alone.

## Nine-stage ROI responses

Counts use the existing `count_roi_flash_responses_chunked` function with
half-open windows, valid coordinates, full event multiplicity and fixed mask
membership. Density is count/169,996 pixels. ON, OFF and total are retained;
global support does not exclude a stage from colour estimation.

| Predicted stage | 1 ms ON / OFF | 10 ms ON / OFF | 100 ms ON / OFF |
|---|---:|---:|---:|
| R1 | 0 / 9,785 | 1 / 33,217 | 159,720 / 38,314 |
| G1 | 0 / 7,188 | 61,969 / 14,931 | 351,501 / 47,769 |
| B1 | 0 / 7,316 | 342,723 / 642 | 117,152 / 446,010 |
| R2 | 0 / 6,185 | 43,876 / 155,715 | 73,343 / 81,249 |
| G2 | 0 / 5,434 | 884 / 123,849 | 122,642 / 25,133 |
| B2 | 0 / 5,074 | 2,215 / 55,700 | 411,564 / 105,065 |
| R3 | 1 / 4,580 | 46,764 / 2,357 | 10,709 / 445,932 |
| G3 | 0 / 4,595 | 28,251 / 19,879 | 188,964 / 21,610 |
| B3 | 0 / 3,858 | 0 / 100,558 | 396,696 / 96,622 |

Each recording directory contains `nine_stage_responses.csv` with exact start/end
times, counts, densities and support labels, plus aligned 50 µs activity plots.

## Repeatability and failed support windows

CV uses sample standard deviation (ddof=1), divided by the mean. There are only
three observations per predicted channel; these are descriptive CVs, not
confidence probabilities or a calibrated pass threshold.

| Recording | Supported windows | Unsupported predicted stages | FULL ON CV: R / G / B |
|---|---:|---|---|
| 1 ms | 6/9 | B1, R2, R3 | 173.21% / undefined / undefined |
| 10 ms | 7/9 | B1, B3 | 86.73% / 100.76% / 171.54% |
| 100 ms | 8/9 | R2 | 92.08% / 53.27% / 53.77% |

Undefined 1 ms G/B CVs mean **zero ON response across all three repetitions**,
not perfect repeatability. Even supported 1 ms stages have effectively no
upper-ball ON signal. The accepted sequence contains 1 ON versus 54,015 OFF ROI
events. Across the full 1 ms recording, the same ROI contains 59,469,698 ON
events, so the selected sequence's scarcity is not a statement that the entire
recording lacks ON activity.

The 100 ms green/blue CVs are lower than the 10 ms case, but are still substantial.
Red ON counts fall from 159,720 to 73,343 to 10,709. The unsupported R2 window
does contain 73,343 ROI ON events, illustrating again that failed global support
is not absence of meaningful recorded events.

An additional diagnostic uses the existing framework's **first 500 µs** after
each predicted onset, holding stage spacing, mask and phase fixed:

| Recording | First-500-µs ON CV: R / G / B |
|---|---|
| 1 ms | undefined / undefined / undefined — all ROI ON counts zero |
| 10 ms | 92.47% / 173.21% / 172.32% |
| 100 ms | 162.15% / 172.12% / 101.82% |

The longer 100 ms integration can average substantial within-window activity.
Its lower FULL CVs therefore do not establish better physical synchronisation.
Equal 500 µs windows control integration duration but can sample different
response phases; they are a diagnostic, not an improved estimator or a timing
reference. All ON/OFF/TOTAL CVs for both modes are in
`channel_repeatability.csv`, with rates in events/effective pixel/ms in the
estimator table.

## Estimator sensitivity

| Recording | ON_PEAK vector | ON_MEAN vector | ON_MEDIAN vector |
|---|---|---|---|
| 1 ms | [1, 0, 0] | [1, 0, 0] | [0, 0, 0] — no median response |
| 10 ms | [0.103585, 0.137265, 0.759150] | [0.172098, 0.172977, 0.654925] | [0.590191, 0.380014, 0.029795] |
| 100 ms | [0.173085, 0.380913, 0.446002] | [0.133042, 0.361900, 0.505057] | [0.111294, 0.286742, 0.601964] |

The 1 ms [1,0,0] is produced by **one event assigned to R3**. The zero median
vector is an absent estimate, not a fourth colour signature. Their arithmetic
L1 difference of 1 is exported for transparency but is not a valid comparison
of two measured colour compositions. The summary figure omits distances involving
zero vectors. Neither normalisation nor the detector's 6/9 pass supplies evidence
of colour quality here.

For 10 ms, the maxima come from R3, G1 and B1. For 100 ms, they come from R1, G1
and B2. The ON_PEAK versus ON_MEDIAN L1 difference is **1.458711** for 10 ms and
**0.311924** for 100 ms. Smaller dependence in the latter case does not establish
colour accuracy. The first-500-µs estimators differ more strongly (L1 differences
approximately 1.859 and 1.719 respectively), and can be sparse.

## Event recurrence across the full recordings

Independent PSEELoader decoding covers **1,837,467,203 events** across the three
DATs. Every saved 1 ms OFF/ON global bin agrees with the project reader, and all
27 exact FULL ROI windows agree with the existing project counter. The 100 ms
native response CSV reproduces exactly. This is decoder/measurement evidence;
it does not independently verify the camera clock or LED timings.

The recurrence calculation uses log(1+count) OFF/ON envelopes with **500 µs**
bins and lag steps, centring each polarity separately for each overlapping
segment. An FFT implementation is tested against direct computation. Broad lag
searches cover 5 ms to min(2 s, one third of segment duration). Configured cycles
are also tested separately, including 4.5 ms.

Five deterministic sections are evaluated per recording: the whole recording,
t0−0.5 to t0+3 s, and up to 4 s from each third of the post-phase stream. These
sections can include startup or differing activity regimes. Both whole-sensor
and common-ROI recurrence curves are exported.

For the context around the selected phase:

| Recording | Configured RGB cycle | Correlation at that lag | Strongest searched lag | Correlation | Correlation at 100 ms |
|---|---:|---:|---:|---:|---:|
| 1 ms | 4.5 ms | 0.420 | 202 ms | 0.860 | 0.787 |
| 10 ms | 31.5 ms | −0.273 | 909 ms | 0.964 | 0.902 |
| 100 ms | 301.5 ms | −0.527 | 329 ms | 0.903 | 0.596 |

The post-phase sections contain further repeatable structure:

- **1 ms:** correlations at 909 ms are 0.963, 0.966 and 0.964; strong peaks also
  occur near 202 ms and other lags. Correlations at the configured 4.5 ms cycle
  are about 0.337. A positive short-lag correlation can reflect a broad response
  envelope; it is not evidence that separate RGB cycles are correctly identified.
- **10 ms:** 909 ms correlations are 0.965, 0.963 and 0.957. The 100 ms feature
  remains strong, around 0.90. The earlier Experiment 1 search was restricted to
  5–200 ms and a shorter interval. Finding a stronger longer-lag match here does
  not contradict that result; it demonstrates search-range dependence and
  additional waveform recurrence.
- **100 ms:** 329 ms correlations are 0.897, 0.904 and 0.930; configured 301.5 ms
  correlations remain about −0.53. Other local peaks include approximately
  984.5 ms and nearby lags, so the waveform has additional recurrent structure.

These are **event-data lags**, with possible harmonics and multiple motifs.
None uniquely identifies physical RGB colour order, controller period, optical
PWM, sensor behaviour or an LED command edge. No baseline cycle is replaced by
202, 329, 909 or 100 ms. Per-recording `recurrence_summary.csv` exports section
boundaries, search limits and the five strongest separated local maxima;
`recurrence_curves.csv` retains the full searched curves.

## Artificial timing sensitivity

Two schemes hold all masks, response durations and stage spacings fixed:

1. Absolute shifts: −2, −1, −0.5, 0, +0.5, +1, +2 ms.
2. Duration-relative shifts: −20%, −10%, −5%, 0, +5%, +10%, +20% of configured fade.

Absolute ±2 ms shifts exceed the 1 ms model's 1.5 ms stage spacing; they are
large cross-stage perturbations in that case. Relative shifts provide an
additional comparison at the same fraction of configured integration duration.
No shifted support score is substituted for the original global support, and
no artificial shift is selected as correct.

| Recording | Maximum ON_PEAK L1 change, absolute scheme | Maximum change, relative scheme |
|---|---:|---:|
| 1 ms | 2.000000, with some shifts also giving zero vectors | 0.000000, same isolated event still maps to R |
| 10 ms | 0.291492 | 0.291492 |
| 100 ms | 0.005573 | 0.225084 |

The unchanged 1 ms vector under ±200 µs shifts is a degenerate single-event
normalisation effect, not robustness. Absolute ±2 ms is only ±2% of a 100 ms
window, whereas the relative scheme reaches ±20 ms. The 100 ms FULL integral is
less sensitive to the smaller absolute shift; this does not validate the phase
or explain its same-colour variation. Per-shift event counts, densities,
ON/OFF/TOTAL CVs and peak/mean/median vectors are exported.

## What this establishes and what to do next

The accepted 1 ms phase supplies effectively no ON feature in the selected
object region. The 100 ms case provides a substantial signal but does not yield
consistent same-colour responses or event-envelope repetition at its configured
RGB cycle. Thus **the observed limitations extend beyond 10 ms**, although the
failure modes differ and their causes are not uniquely established.

This is not a ranking of which illumination duration is intrinsically best:
there is one recording per nominal setting, only one selected nine-window
sequence per recording, unverified physical colour labels, different detector
search histories, possible object/camera differences, and unequal FULL
integration durations. Lower CV, less estimator dependence or a stronger
autocorrelation alone cannot establish colour accuracy or hardware timing.

Before purchasing equipment, the next useful work with existing resources is
to audit the Arduino timing implementation/configuration, compare accepted
phases under a consistent search protocol, and evaluate whether detector passes
also supply adequate per-ROI ON features and repeated-cycle evidence. Report
counts and per-cycle variation alongside every vector; explicitly distinguish
zero/sparse estimates from useful measurements. Such quality checks should be
evaluated separately rather than silently modifying this baseline or optimising
phase for plausible displayed colours.

Independent LED command/optical timing, a camera-clock relation and a known
first-red reference will still be needed to validate a physical synchronisation
fix. Calibrated colour reference measurements are a separate requirement for
claiming colour accuracy. The present comparison does not demonstrate a sensor
fault, optical PWM cause, corrected period or calibrated colour reconstruction.

## Reproduction and outputs

From the repository root, use a new output directory:

```bash
python3 run_recording_comparison.py \
  --output diagnostics/experiment_2a \
  --sensitivity

python3 -m unittest discover -s tests -v
git diff --check
```

The DATs, listed saved runs and previous Experiment 1 evidence must be available
locally. `--toolbox` overrides the default sibling Prophesee toolbox path.
The script rereads all three DATs and reruns the two additional detectors; it
does not invoke interactive ROI selection. All seven tests pass, including the
new FFT/direct-correlation checks and the previous diagnostic fixtures.

Completed CSV summaries can be replotted without rereading the recordings:

```bash
python3 run_recording_comparison.py \
  --output diagnostics/experiment_2a \
  --summarize-existing
```

The first run's source hashes and exact command remain in `evidence.json`.
`analysis_source_snapshot.py` preserves the executed source before a subsequent
summary-only display correction that marks undefined CVs and omits zero-vector
distances from the figure. `summary_refresh.json` records the current summary
source and input CSV hashes. Raw counts, detector results and earlier Experiment
1/1D outputs were not changed by the summary refresh.

| Output | Contents |
|---|---|
| `comparison.csv`, `REPORT.md`, `evidence.json` | Main results, assumptions and provenance |
| `common_mask.npz`, `common_roi_comparison.png` | Identical transferred geometry and placement check |
| `channel_repeatability.csv` | Per-channel ON/OFF/TOTAL CVs for FULL and FIXED_500US |
| `estimator_comparison.csv` | Existing peak/mean/median estimates, rates and nonzero flags |
| `sensitivity_vectors.csv` | Both timing-shift schemes and estimator changes |
| `repeatability_and_estimators.png`, `timing_sensitivity.png` | Cross-recording comparisons |
| `<recording>/nine_stage_responses.csv`, `timing_support.csv` | Nine individual predicted stages, densities and original support scores |
| `<recording>/aligned_activity.png`, `same_colour_repetitions.png` | Global/ROI traces and individual responses |
| `<recording>/raw_activity_50us.npz` | Full-recording independent global/ROI OFF/ON counts and exact stage checks |
| `<recording>/recurrence_*.csv`, `recurrence.png` | Multiple sections, lag limits and candidate local peaks |
| `<recording>/sensitivity_*.csv` | Shifted individual responses and repeatability |
| `1ms_2s/pipeline/`, `100ms_10s/pipeline/` | Unchanged detector reruns and chronological search logs |
