> **Superseded for the 16 November session:** use [the final 21-recording plan](recording_plan_2026-11-16.md), [checklist](recording_checklist_2026-11-16.md) and [firmware instructions](../arduino/README.md). This document is a historical planning record; its fixed-firmware restrictions and extra experiment lists are not the active session scope.

# New recording campaign — a controlled basis for timing and colour experiments

Status updated 15 November 2026: **the original Uno firmware must be preserved;
current controller work is read-only**. Use the
[fixed-firmware protocol](recording_campaign_fixed_firmware.md) for the immediate
session. The adjustable duration/drive matrix and rectangular pulses below are
a future design contingent on an independently adjustable controller. They are
not executable instructions for the current board. Adding controller logs,
preambles or a stage-gate output is also deferred unless already supported by
the existing firmware. This protocol does not change Yan's detector or colour
estimator.

## The research experiment

Primary question: with independently identified illumination stages, how
repeatable and discriminative are the object ROI's colour-related event
responses, and how do timing uncertainty, optical drive and integration duration
affect them?

The previous recordings show why a new dataset needs more than additional
durations: automatic timing can pass with almost no object ON signal; global
support does not certify an ROI response; waveform recurrence does not establish
LED timing. Acquire command timing, optical evidence where available and
reference targets alongside the events.

The staged campaign below separates setup debugging, controlled comparisons and
model evaluation. Numbers of cycles/takes are proposed practical starting points,
not a statistical power calculation or a promise of universal colour recovery.

## 1. Fix the setup and record its configuration

- Mount the camera, LEDs and target; mark their positions and distances. Keep
  focus, aperture, camera position and room lighting fixed through the core
  comparison. Photograph the complete arrangement and target labels.
- Use diffuse, matte surfaces and a plain background for the initial controlled
  scene. Put white, middle-gray and black reference patches alongside matte R,
  G, B, C, M and Y patches. Keep the original ball as an application target after
  reference-patch behaviour is understood. Several targets can share one scene.
- Borrow a chart with documented patch values/reflectances if available. Ordinary
  coloured cards supply category/object identity, not calibrated sRGB truth.
  Save a conventional-camera reference under a fixed white illuminant with
  manual exposure/white balance. A photograph alone is not calibrated colour
  ground truth or event-camera clock synchronisation.
- Record exact camera model, serial, SDK/firmware, resolution, lens, focus,
  aperture, full bias/configuration JSON and all on-sensor processing settings.
  Do not change bias settings and LED intensity together when testing a cause.
- Keep acquisition filters fixed during the core campaign. Anti-flicker and
  temporal filters can remove the illumination response of interest; event-rate
  control can drop events. A clean acquisition with these off is useful only if
  it remains within the camera/USB/storage bandwidth. First reduce the optical
  load and validate capture. Any comparison with ERC/filter settings changed is
  a separately labelled diagnostic, not an unnoticed change to the baseline.
  See [Prophesee's camera-settings guide](https://support.prophesee.ai/portal/en/kb/articles/build-your-event-based-application-2-5-camera-settings).

## 2. Establish what the LEDs actually do

Audit and archive the Arduino source, compiled build identity, board, driver,
pins, clock/timer configuration and sequence configuration. Distinguish
`on_us`, `ramp_up_us`, `hold_us`, `ramp_down_us`, `dark_us`, PWM period/duty,
inter-stage overhead and inter-cycle pause. Avoid a parameter named “10 ms”
whose meaning could be a ramp step, full ramp, each half-ramp or complete stage.

For the first controlled baseline, propose a rectangular command:

```text
R on → all RGB off → G on → all RGB off → B on → all RGB off
```

Hold the chosen optical drive during each on interval. Measure the optical
rise/fall: a rectangular command does not guarantee a rectangular optical pulse,
and abrupt steps can themselves create high event-rate bursts. Test a legacy
fade separately at one matched operating point after this baseline works.

If brightness uses PWM, label the factor as PWM duty cycle and record carrier
frequency, duty and pulse phase. Do not interpret it as an isolated amplitude
change. If an existing constant-current control or characterised optical
attenuation is available, that can separate optical amplitude from PWM duty;
log exactly which method is used. Equal R/G/B command values do not mean equal
optical power. See [Arduino's PWM description](https://docs.arduino.cc/tutorials/generic/secrets-of-arduino-pwm).

Preferred timing arrangement:

1. Record a controller stage-gate signal with camera Trigger In: high during the
   commanded stage, low during the off interval. Store both edges, an unambiguous
   block-start pattern, stage index and ordered colour list. A single trigger
   line does not encode colour identity by itself.
2. Measure LED output with a photodiode and oscilloscope/logger that also records
   the controller signal. Save numerical traces and sampling information, not
   only screenshots. A photodiode's response can differ by wavelength; its
   uncalibrated amplitudes are not comparable RGB optical powers.
3. Verify the camera trigger edge polarity, count, timing origin and timestamp
   relationship on a short file. Follow the particular EVK's electrical/connector
   specification when wiring; do not assume a generic GPIO connection.

Trigger In adds timestamped marker events to the camera stream; it does not
start camera recording. A controller marker measures a command, while the
photodiode measures emitted light. These are separate references. See
[Prophesee timing interfaces](https://docs.prophesee.ai/stable/hw/manuals/timing_interfaces.html).

If no photodiode is available, capture controller timing on existing lab
instrumentation and document optical timing as unverified. If there is no
electrical trigger connection either, record a distinctive visible optical
preamble at the start and end and retain a reference patch in view. This is an
event-derived alignment aid, not independent optical timing ground truth. Do not
claim sub-millisecond synchronisation from host serial-message arrival times.
Buffer controller logs for export after time-critical output, where possible;
logging must not silently alter the sequence.

Record controller timestamps as controller-clock time, camera timestamps as
camera-clock time and scope/logger timestamps as their own clock. Preserve
matched start/end markers to estimate offset and drift; never merely subtract
one clock's first timestamp from another clock's measurements.

## 3. A small pilot before the main matrix

Use the reference-card scene, a 10 ms commanded on duration and initially generous
off intervals. These are pilot choices, not replacement values for old files.

Record the following short controls with the same camera configuration:

| Control | Purpose |
|---|---|
| Static scene, RGB emitters off, 5–10 s | Ambient flicker and background activity |
| Steady commanded R, G and B separately, about 5 s each | Persistent modulation despite an apparently steady command |
| One colour at a time, 30–50 on/off pulses | Response latency, ON/OFF waveform, recovery and repeatability without colour-order ambiguity |
| Uniform matte gray/white target under repeated pulses | Check horizontal structure without the ball's sector geometry |
| Repeated RGB sequence at low/middle/high drive | Find an operating range with measurable target response and manageable event load |

Allow and log the same camera/LED warm-up procedure. Repeat a fixed reference
condition between blocks to reveal drift rather than attributing it to the
next experimental factor.

For the brightness pilot, keep durations, LED waveform, sensor biases and
geometry fixed. Select three drive levels empirically: low with a detectable
reference response, middle with comfortable capture margin, high as a controlled
stress condition that remains technically recordable. Save actual drive values
and control method, not just “25/50/100% brightness”. Do not tune channels or
biases to make a ball look a desired colour.

Check candidate off intervals of 0.5, 5 and 20 ms. Examine the reference ROI's
return towards its pre-pulse activity and the optical trace, if available. Choose
a common core off interval D only after testing recovery at the three proposed
on durations/drive levels. If none is adequate, test longer gaps. A commanded-off
interval means the experimental emitters are off; ambient illumination may remain.

Horizontal bands are not a diagnosis. Prophesee documents saturation, lighting
and event-rate-control effects as possible sources of horizontal artifacts.
Compare the raw count maps, row activity, optical trace, event-rate peaks and
recording/decoder warnings under one changed factor at a time. Disabling ERC
without reducing event load can replace one distortion with another capture
failure. See [Metavision Studio guidance](https://docs.prophesee.ai/stable/metavision_studio/).

If RGB duty-cycle changes alter the bands, that supports a dependence on that
operating condition; it does not uniquely prove a saturation or PWM cause.
Retain the problematic pilot recordings as labelled stress/diagnostic cases.

## 4. Core controlled dataset

After the pilot, freeze geometry, camera configuration, waveform definition and
the verified common off interval D. Define each drive level as a three-channel
tuple, e.g. L=(R_L,G_L,B_L), rather than assuming channels have equal output.

| Factor | Proposed levels |
|---|---|
| Commanded on duration | 1, 10, 100 ms |
| LED drive | L, M, H, with actual per-channel values recorded |
| Independent recording takes | 3 per condition |
| Main measurement block | 100 complete RGB cycles per take |
| Off interval | Common pilot-validated D |
| Stage order | Known R,G,B throughout the main block |

This is **3 × 3 × 3 = 27 recordings**, using the same targets in the same scene.
The supplied schedule has three independently randomised blocks, each containing
all nine duration/drive conditions. Stop/restart acquisition between takes;
100 cycles from one recording are not 100 independent sessions. Repeat the
reference condition between blocks and log any drift or configuration change.

Each recording contains:

```text
2 s RGB-off baseline
distinctive start marker / known first-colour preamble
fixed, explicitly flagged settling cycles, if needed
100 labelled RGB measurement cycles
distinctive end marker
2 s RGB-off baseline
```

The preamble and settling segment are outside the 100 measurement cycles and
have their own logged timing. Choose their definition before the core campaign;
do not retrospectively relabel their peaks as measurement stages.

Do not use recording length as a substitute for cycle count. Excluding preambles
and settling, main-block duration is 100×3×(on_us+D), and the saved clip needs
that duration plus the baselines. For illustration only, D=10 ms gives main
blocks of 3.3, 6 and 33 seconds for the three on durations. Actual D remains a
pilot outcome. Estimate total storage from measured pilot bytes/second and
planned durations; retain native RAW even if working DAT exports are large.

If time becomes tight, prioritise timing verification, controls and three
independent takes at the middle drive across all durations, then expand L/H.
Document the reduced design rather than quietly collecting unbalanced conditions.

## 5. Small follow-up blocks for confounds and generalisation

Keep these outside the initial full factorial rather than varying every factor
simultaneously:

- **Dark-gap effect:** at the middle drive and 10 ms on duration, compare
  0.5/5/20 ms off intervals, three takes each. Existing matching core takes can
  be reused if their configuration is identical. These intentionally stressful
  conditions may not satisfy the settled-baseline criterion; label them as such.
- **Order/history:** at one working condition, record all six RGB permutations
  if practical. A shifted order such as RGB→GBR changes the starting phase but
  preserves cyclic predecessor relationships; it is not a full carry-over test.
- **Legacy waveform:** compare the audited original fade/PWM programme with the
  rectangular baseline at one explicitly defined condition. Optical traces must
  describe how their durations/outputs differ; do not call unmatched light
  profiles equivalent simply because their settings use the same number.
- **Model generalisation:** at a working middle condition, collect three new
  layouts/object sets, three takes each. Move patch positions and include
  different physical samples of the same labelled colour classes. Save each
  scene's ROI geometry and reference photo. Include the original ball here.
  Add controlled motion or changed ambient lighting only after the static
  acquisition is understood and label those factors separately.

A nine-patch static chart mostly supports calibration and pipeline development.
Repeated cycles of the same patches do not create broad material diversity.
For learning experiments, partition by recording/session and physical target
instance/layout; keep every event/window from a take together. Do not randomly
split adjacent bins or repetitions into train and test, or allow a model to
identify a colour only from its fixed image location. Reserve held-out data
before fitting thresholds or colour mappings. Three takes per condition alone
do not establish independent object/material generalisation.

## 6. Keep the information needed for future models

For every take retain:

- Native event `.raw`, plus working CD DAT export if needed. Also retain external
  trigger events as their own export with timestamps/edge/channel, and the
  original time origin. The current project decoder reads CD DAT types 0/12,
  not the separate external-trigger type 14; a CD-only export cannot replace
  the trigger record. The DAT specification supports distinct event types:
  [Prophesee DAT format](https://docs.prophesee.ai/stable/data/file_formats/dat.html).
- Complete camera settings; original controller source/build/config; electrical
  and optical timing traces; trial metadata; start/end markers; event-rate and
  decoder/capture diagnostics. RAW preserves captured data, not events already
  dropped by hardware filters or bandwidth limits.
- A stage table with run/block/cycle/stage index, commanded colour and drive,
  commanded on/off timestamps and clock identifier, measured trigger timestamps,
  optical edges where available, mapping method and timing uncertainty. Preserve
  absent measurements as missing, not inferred ground truth.
- Scene/patch/object IDs, material labels, reference chart/photo information,
  ROI polygons/effective masks, setup photo, geometry and environmental notes.
- A manifest linking every artifact to one immutable run ID and experimental
  condition. Calculate checksums and keep a second copy before leaving.

The current automatic diagnostics select nine stages and several scripts have
case-specific timestamps. They do not yet validate 100-cycle acquisitions or
new trigger exports automatically. Before the core campaign, demonstrate a
complete short **capture → save → reopen → read triggers → identify stages →
count the same ROI** round trip, then adapt the acquisition QC to all planned
cycles while reusing the existing ROI counter. Do not discover format/timestamp
incompatibilities after the session.

## 7. On-site checks and decision rules

Separate capture validity from scientific performance. An intentionally weak or
poorly repeating condition can be useful data; missing timing logs or corrupted
files cannot be repaired by choosing a more plausible colour.

Before running the full matrix, confirm on a pilot:

- [ ] RAW and derived files reopen; timestamps, event types and origins are understood.
- [ ] Both trigger edges and the first-colour/stage mapping can be recovered.
- [ ] Measured optical pulse shape and recovery are saved, or their absence is explicit.
- [ ] Expected cycle/stage counts match the programme; truncations are flagged.
- [ ] White/gray reference patches show measurable responses for each channel;
      weak black/absorbing patches are not forced to respond.
- [ ] Peak event load and capture logs show no observed overflow/decoder/data-loss
      issues; absence of warnings alone is not proof of lossless capture.
- [ ] Every camera/LED setting and geometry identifier is saved.

After every take, run a quick report before continuing:

- Global and ROI ON/OFF histograms with measured markers and predicted windows.
- ROI counts/densities for **every cycle**, valid/zero/sparse-response flags and
  per-colour median, spread and CV. Separate onset, sustained and offset activity.
- Row-wise activity and spatial maps for representative on/off transitions;
  note banding without assigning its cause.
- Trigger/optical duration distributions and start/end clock mapping residuals;
  report timing uncertainty relative to the shortest on/dark interval.
- Fixed-reference response drift, event-rate peaks and file-integrity checks.

Re-record a technically incomplete take while the setup is available. Keep and
label valid takes whose responses are inconsistent. Freeze any chosen signal
adequacy/technical acceptance criteria after the pilot; numerical thresholds
are not universal sensor specifications. No high CV or unexpected colour alone
justifies erasing a recording from the dataset.

## 8. Evaluation this dataset enables

Compare Yan's unchanged phase estimator with a proposed method against trigger
and optical references. Report phase/duration error, missed/false stages,
clock drift and failure rate, including weak-signal conditions.

For colour-related features, reuse the existing ROI extraction and compare ON,
OFF, net response, onset/offset integration and peak/mean/median aggregation.
Measure per-cycle and independent-take repeatability, sensitivity to artificial
timing errors, and class/patch separability. Compare both full-duration and fixed
integration intervals where appropriate. Reference-normalised features need
their own validation; do not tune LED ratios to force desired display colours.
Keep the number of repetitions equal when comparing aggregation rules: Yan's
baseline takes maxima over three repetitions. A maximum over 100 repetitions is
a different estimator with different outlier sensitivity. Evaluate the original
rule in predeclared groups of three and use the full series for repeatability
analysis; study aggregation length separately if desired. A white patch is not
expected to generate equal RGB event counts under unequal light spectra/output.

Evaluate on held-out takes, layouts and physical material instances, then on a
held-out lighting/duration condition. Category labels support classification
experiments; calibrated RGB/reflectance error requires corresponding independent
reference measurements. An event-derived response signature is not automatically
a calibrated RGB value.

## Prepared local artifacts

- `experiments/recording_campaign_schedule.json`: original future-design trial
  order, deferred under the current preserved-firmware constraint.
- `experiments/fixed_firmware_schedule.json`: immediate proposed pilot/take order;
  non-nominal optical attenuation conditions require available characterised optics.
- `experiments/recording_manifest_template.json`: per-take metadata checklist.

The adjustable matrix remains a future proposal. The fixed-firmware schedule
now records command timing targets confirmed by the offline binary audit;
actual electrical/optical durations remain unmeasured. These planning artifacts
are not commands to connected hardware and do not identify physical LED output.
