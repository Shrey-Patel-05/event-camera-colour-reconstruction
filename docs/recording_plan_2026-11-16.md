# Final recording plan — 16 November 2026

Status: **agreed scope, 21 independent recordings**. Updated 16 November 2026. This plan supersedes the previous 30–60 minute proposal and the earlier fixed-firmware/adjustable campaign schedules. No additional recordings are included. The user-approved amendment makes L1/L2 reconstructed original modes in the same firmware, rather than restored-binary recordings. The original firmware backup, historical recordings and existing analysis code remain preserved.

The two research directions are (1) distinguishing genuine illumination transitions from interfering events, including irregular schedules, and (2) learning a mapping from event-derived RGB signatures to reference colours. Keep the ball for comparison with Yan's setup and use physical colour swatches as the primary calibration targets. Fruit is outside this session.

The machine-readable source is [session_2026-11-16.json](../experiments/session_2026-11-16.json). Use the [recording checklist](recording_checklist_2026-11-16.md) in the lab and the [firmware instructions](../arduino/README.md) to prepare the board. The new firmware is implemented and can be compiled offline; physical operation and optical timing still require verification on the actual apparatus.

## Agreed recordings

| ID | Experiment | Recordings | Purpose |
|---|---|---:|---|
| L | Reconstructed original firmware | 2 | Reproduce audited ramp/PWM logic and investigate recurrence of abnormal peaks/horizontal bands; not exact binary reproduction |
| N | RGB LEDs off | 2 | Measure background activity without flashes |
| S | R-only, G-only, B-only, each 10 ms ON / 20 ms OFF | 3 | Characterise individual LED responses |
| T1 | Sequential RGB, 1 ms ON / 0.5 ms OFF | 1 | Test fast flashing close to Yan's assumed timings |
| T2 | Sequential RGB, 1 ms ON / 5 ms OFF | 1 | Investigate longer recovery intervals |
| T3 | Sequential RGB, 5 ms ON / 5 ms OFF | 1 | Investigate longer illumination |
| C-A | Selected T1–T3, original sample positions | 3 | Repeatability across independent recordings |
| C-B | Same selected sequence, swatches moved between positions | 2 | Spatial dependence and possible pixel-response variation |
| D | Same selected sequence, original positions restored | 1 | Drift and repositioning effects |
| J | Irregular RGB, variable gaps and omitted flashes; exact saved schedule | 2 | Detection without assuming a fixed repeating pattern |
| M | M1 LEDs off/moving; M2 flashing/stationary; M3 flashing/moving | 3 | Interference from motion-generated events |
| **Total** | | **21** | |

OFF always means all three RGB channels off between successive colours. T1/T2/T3 nominal complete RGB cycles are 4.5/18/30 ms respectively. Digital programmes command one colour at a time, without PWM or a brightness ramp. These new command targets do not establish the timing of historical DAT recordings. The provenance of the installed original binary to every old recording remains unverified; L tests reconstructed original flashing logic, with no claim of exact binary or optical waveform reproduction.

## Order and fixed conditions

Use one uploaded recording_session sketch for **all 21 recordings**. `RUN L1` and `RUN L2` select the reconstructed legacy mode. The original application has already been replaced; this plan requires no HEX restoration. Retain the backup/hash and audit as evidence. Record L1/L2 as `reconstructed_original_firmware` with `exact_binary_reproduction=false`.

Keep camera position, focus/aperture, biases, filters, LED drive/position, ball position, ambient light and box opening state fixed where comparisons require it. Record any unavoidable change. Changing between legacy PWM and digital modes compares whole illumination programmes, including their different optical dose; equal nominal command timing would not make them radiometrically equivalent.

Set up the fishing line and separate object before L if possible. Park the object outside the sample ROIs and keep the line route/opening unchanged throughout. Keep it parked during L–J. This avoids adding a new light leak or changing the scene immediately before M. Use the same object/path for all three M recordings.

Use fixed white and middle-grey reference patches in view. Label and retain the actual physical swatches; photograph the patch-ID/position map for layout A, layout B and A restored. For C-B, move individual swatches between well-separated positions while leaving camera, light, ball and reference patches fixed. Main colour samples never move during a recording.

## Duration and acquisition

The new firmware runs a finite block only after an explicit RUN command and stays off afterwards. Each **digital** flashing block has:

1. 1 second with all RGB off.
2. Distinctive start pattern: R 20 ms, G 40 ms, B 80 ms, with 20 ms all-off after each pulse.
3. 500 ms all-off settling interval.
4. Measurement sequence.
5. 1 second all-off ending interval.

The preamble is an alignment aid, and its responses/settling interval are excluded from colour measurements. It contains all three colours even in S; **only the measurement phase** is R-only, G-only or B-only. N and M1 have no optical preamble at all, since they are LEDs-off controls. L has no newly added marker. It uses only the audited one-second all-zero startup before the reconstructed stages, without the digital marker/settling/post-dark sequence.

S uses 100 pulses per colour (3 seconds of measurement). T/C/D/M2/M3 use at least 100 RGB cycles and at least 3 seconds of measurement: T1 = 667 cycles, T2 = 167, T3 = 100. Resulting measurement lengths are 3.0015, 3.006 and 3 seconds. New flashing takes are therefore roughly 5.7 seconds including context/preamble; J varies slightly. N/M1 contain 5 seconds of dark measurement plus the two 1-second dark context intervals. For L, start capture before RUN and retain the one-second startup plus at least five seconds of repeated RGB stages through DONE. Stop occurs only after a complete RGB cycle; DONE records actual controller duration and completed cycle/stage counts. Optical cycle timing is not independently verified.

Start the camera recording first, then issue the run command. Stop after DONE and a little capture margin. Restart camera acquisition for each take. Preserve native unbinned events, timestamps and polarity; preserve RAW if available and any derived DAT plus conversion settings. Verify that any trigger events are saved separately or retained in native files with a shared timestamp origin. A CD DAT file alone does not prove that trigger events were retained.

Keep acquisition processing documented. Anti-flicker, trail/STC and event-rate control can suppress or drop the very events needed for PEA/TFE/IET. Use a fixed supported configuration with adequate throughput, inspect drops and avoid silently changing filtering between conditions. Prefer reducing excessive optical/event load before altering the core comparison.

## Selecting C

After T1–T3, select exactly one of those schedules using timing evidence, reference-ROI response separation and acceptable event throughput. Record the reason and selected profile. The single-take screen is a practical operating-point choice, not a statistically established best timing.

C-A, C-B, D, M2 and M3 must use that same choice. J uses its ON width and a gap rule specified below. The prepared bundle writes the selected profile into every dependent command and metadata record. Firmware refuses a dependent run without an explicit T1/T2/T3 argument. If none is usable, flag this as a constraint and discuss a change before substituting a new schedule or adding experiments.

## J: saved irregular schedules

J1/J2 are different deterministic, saved sequences, with seeds 2026111601 and 2026111602. Each has 300 intended slots. Colour order is shuffled within RGB triples; each colour therefore occurs in 100 intended slots. Exactly one randomly placed slot per block of ten is omitted: 30 omissions and 270 emitted measurement pulses per recording. Omission counts per colour need not be identical.

Use the selected C ON width. Base gap = max(selected C OFF interval, 5 ms), with each gap chosen from 1, 2 or 4 times that base. The 5 ms lower bound is an implementation choice for this agreed variable-gap condition; it is not a claim that 5 ms recovery is sufficient. An omitted flash remains entirely dark for its intended ON interval and its following gap. It does not emit a gate or illumination transition.

Both realised colour/omission/gap tables are saved in experiments/irregular_2026-11-16_J1.csv and J2.csv. Preparing a bundle with the chosen T profile exports every target onset, offset and slot boundary, including the preamble. Retain omitted slots as negative examples. The aim is to detect actual emitted transitions without inventing an edge simply because a regular cycle predicts one.

## M: fishing-line movement interference

Use fishing line/string through the existing opening to move a separate small object from outside the black box. Keep all main samples and reference patches stationary. Move the object through a designated separate part of the field of view, away from sample ROIs; avoid camera shake and illumination occlusion. Record object identity, path and approximate movement procedure. String visibility and any shadows are part of the interference and should be noted.

| Run | RGB illumination | Separate object |
|---|---|---|
| M1 | Off throughout, including no optical marker | Moving |
| M2 | Same selected C-A schedule | Stationary, parked at a documented position |
| M3 | Same selected C-A schedule | Moving along the same route as M1 |

For M1/M3, begin moving before the measurement block and continue until DONE so the measurement interval includes motion. Human movement is approximate; host/serial timestamps are not precise motion ground truth. M1 and M3 test moving-object events; motion events are real scene activity, not necessarily sensor noise. M2/M3 reuse the exact same LED timeline. Their object state is the changed factor.

## L: reconstruction supported by the audit

The reconstructed stage clears D9/D10/D11 using analogWrite zero; samples elapsed time while below 500 microseconds; updates selected brightness as `floor(elapsed_us * 255 / 500)` when eligible; requests 255 at the endpoint; immediately clears all three pins; then waits a separate 500-microsecond zero-command interval. There is no peak hold or ramp-down. Updates skip nonselected tuple components, as established at 0x0536–0x05de. The loop repeats D9/red -> D10/green -> D11/blue and clears all outputs again after each RGB cycle.

Intermediate analogWrite values use the audited Timer1/Timer2 8-bit phase-correct /64 PWM; at nominal 16 MHz its period is 2.040 ms. Zero/255 use digital endpoints. The programme does not synchronise timer counters, since phase was not established. Timer control/compare registers are saved and restored, and all channels are cleared before returning to command mode.

The source follows known control flow, but compiler/core overhead, PWM phase and optical waveform are not reproduced from the binary. Serial selection, a fresh startup wait per RUN and finite termination after at least five seconds are recording-wrapper differences from the original continuous loop. Metadata and START/DONE identify these limitations explicitly. No invented per-edge optical or fixed-cadence timeline is exported for L.

## Timing labels and firmware requirements

For digital modes, the prepared firmware/configuration provides the complete ordered **command target timeline** and a matching run ID. L1/L2 instead export an elapsed-time ramp recipe and report actual completed cycles, since software overhead determines each ramp sampling pattern and stage spacing. It uses absolute micros-based deadlines to avoid accumulating a separate delay error every stage. It reports controller run origin, completion, maximum observed software lateness and emitted-edge count after timing-sensitive execution. No serial logging occurs inside the pulse sequence.

These targets are not independent optical timestamps. Digital writes, 4-microsecond Uno clock quantisation, interrupts, driver delay and optical rise/fall remain relevant. The firmware records aggregate software timing diagnostics, not a measured timestamp for every GPIO edge. For digital modes, if a deadline is over 100 microseconds late before an operation, it aborts to off rather than compressing the remaining timeline; flag such a take incomplete. No automatic rerun occurs.

Hardware Trigger In/photodiode use is conditional on existing verified equipment. The new build does not drive a trigger pin. Verify the actual camera interface and electrical/polarity specification before making a connection; software alone cannot add independent optical ground truth. Without that evidence, retain event-derived alignment and provisional timing labels, and qualify TFE/supervised timing claims. Treat controller, camera and host clocks separately. A start pattern can estimate alignment; it does not certify optical timing or clock drift.

## Colour references and later analysis

Physical paint samples are useful stable targets. Their IDs and nominal manufacturer colours are not measured CIELAB values. Keep the samples so stronger reference labels can be added later. CIELAB belongs at the colour-mapping/output/evaluation stage: response features -> reference L*, a*, b*, with a declared reference white/measurement method. A suitable reflective-sample colourimeter/spectrophotometer or validated photographic profiling method can provide those labels. Ordinary photographs still document identity and geometry.

Retain raw magnitudes, total response, normalised signatures, reference patches and per-pixel maps. This supports per-pixel response studies and PEA/TFE/IET without committing to one estimator. C-B can expose spatial dependence, but does not by itself separate sensor variation from illumination-field/lens variation.

## Information to extract later

Preserve all raw `(x, y, t, polarity)` events. Derive multiple representations later rather than recording only binned visualisations.

| Information | Proposed extraction | What it tests |
|---|---|---|
| Transition evidence | Global, reference-ROI and target-ROI ON/OFF time traces; initially 50–100 microsecond bins plus exact timestamps | Spatial origin, polarity, extra bursts, response tails, missing/weak responses |
| PEA/count features | Per-pixel positive counts after onset, negative counts after offset, area-normalised ROI counts, active-pixel fraction | Count-based baseline, weak-response coverage, ON/OFF asymmetry |
| First-event latency | First relevant-polarity event per pixel relative to independently known onset/offset | Latency information, provided timing uncertainty is sufficiently small |
| IET | Successive relevant-polarity event intervals within the same pixel and response window | Within-response dynamics; never pool inter-pixel arrival times and call that per-pixel IET |
| Response shape | Cumulative counts at several early windows, late-window counts, time quantiles and tail duration | Whether the important information is confined to transitions or continues through the pulse |
| Spatial structure | Per-pixel count/latency/validity maps, row profiles and reference-patch comparisons | Bands, fixed spatial response and changing illumination footprint |
| Colour signature | R/G/B feature vector with counts, timing, validity, total magnitude and optional reference-normalised versions | Whether timing adds predictive colour information beyond counts |

Use both fixed-duration early windows and full physical pulse windows. Longer windows automatically allow more background events; dividing counts by duration does not make an edge response a steady intensity measurement. Restrict windows so adjacent flashes and the opposite edge are not unintentionally mixed.

No first event is a missing/right-censored latency, not zero latency. IET requires at least two eligible events from the same pixel; report valid-pixel fractions. A zero count is a valid count observation but not evidence of perfect repeatability. Report robust spread and CV only where its mean denominator is meaningful.

For reference normalisation, retain raw and adjusted data. Ratios of nonlinear event counts are empirical features, not automatically reflectance. Avoid dividing by a near-zero reference response, and do not assume dividing TFE by a white-patch TFE has physical justification.

## Evaluation that keeps the two ML directions distinct

Synchronisation: compare a conventional polarity-aware peak/change detector with a learned detector using independently established command/optical labels. Report precision/recall with one-to-one matching at a declared tolerance, missed and extra transitions, false positives per second during no-flash periods, timing-error quantiles and phase drift. Evaluate on entire held-out recordings, layouts and irregular seeds. Distinguish true RGB transitions from PWM carrier edges if the target is stage detection. Trigger values and marker ROIs used to build labels must not leak into an event-only model's inputs.

Colour calibration: compare the preserved ON_PEAK baseline, robust count summaries, count-plus-timing features and reference-calibrated features. Start with small regularised regression models before larger networks; sample diversity is limited. With valid reference colours, evaluate perceptual error, lightness error and repeatability. Without them, evaluate sample/category discrimination and signature stability, explicitly leaving absolute colour accuracy unresolved.

Reserve whole physical swatch IDs/shades for colour generalisation tests, not just random pulses. Also report the easier task of recognising familiar samples in new recordings. Separate held-out layouts from held-out colours: these answer different questions. Fit scaling, calibration and model selection using training data only. A few dozen swatches make this exploratory; include uncertainty and avoid claiming that thousands of pixels are thousands of independent colour examples.

Use two timing modes for every promising colour model: independently referenced alignment and event-estimated alignment. The first estimates how well colour can work when timing is known; the second reveals the additional loss from synchronisation. This supports both project directions without forcing an early choice.

## Minimum saved metadata

- Run ID, acquisition time/date, actual duration, take number and scene/layout ID.
- Physical sample IDs, patch-to-position map, ball-sector labels and ROI provenance.
- Camera model/serial, resolution, lens settings, biases, filters, ERC settings/drop indicators, SDK/acquisition version.
- Firmware/source/build identity; old firmware hash where applicable; confirmed pin-to-colour mapping/polarity.
- ON and all-RGB-off durations, waveform type, order, intended/observed cycle count, PWM carrier/duty if used, actual optical measurements if any.
- Timing-reference type and uncertainty; trigger channel/polarity; clock origins, marker records and any timestamp shifts during export.
- LED drive/attenuation, geometry, room/background-light state, warm-up and settling procedure.
- Native raw file and derived DAT paths, associated trigger/trace files, setup/reference photographs and observations of failures or clipping/drop behaviour.
- Random seed and full realised stage list for irregular sequences, including intentionally omitted slots.
- Reference-colour method and values when available; leave unmeasured values empty rather than inventing them from a visual swatch.

## Practical constraints and completion criteria

- **Scope is 21 recordings.** The old 30-minute core/60-minute extras split is retired. Setup, firmware upload, sample rearrangement and file verification dominate the time; do not promise completion in 30 minutes. If time runs out, mark outstanding agreed IDs unrecorded and discuss rescheduling rather than replacing the scope.
- **L identity:** the accepted substitute is now reconstructed source behaviour. Do not label L1/L2 as the original binary or use its nominal 3 ms RGB budget as measured optical timing. No restoration is required.
- **Hardware verification:** physical D9/D10/D11-to-colour mapping, active polarity, driver/current limits and finite full-brightness pulses must be checked. The supplied build defaults to refusing RUN until the hardware configuration is confirmed; unverified pins remain inputs.
- **C selection:** no usable T1–T3 means the dependent colour and flashing M recordings cannot be completed as agreed without discussing a revision.
- **Timing instrumentation:** missing camera-trigger/photodiode equipment limits timing truth and absolute TFE interpretation; it need not prevent acquisition of useful provisional data.
- **Capture/storage:** high event bursts or sensor filtering can invalidate counts/timing features. Inspect event-rate/drop indicators and test file readability before collecting many takes.
- **Movement route:** the opening must permit repeatable external motion without box light changes, shaking the camera or moving the main targets. Establish it before comparisons.
- **Colour labels:** swatch-only recordings support repeatability/discrimination now; numerical colour-calibration accuracy awaits appropriate reference measurements.

A completed session has 21 identifiable independent files, settings/layout provenance, saved commanded schedules for the new firmware, serial reports, and retained raw ON/OFF data. Scientific weak responses are retained and flagged. A technical retake should be marked as a replacement of its agreed run ID with a suffix and reason, rather than counted as a new experiment.

## Evidence and preserved records

The [firmware audit](arduino_firmware_audit.md) establishes commanded ramp/dark behaviour of the supplied binary, with optical timing unmeasured. [Experiment 1](experiment_1_findings.md) and [Experiment 2A](experiment_2a.md) show why detector support cannot substitute for independently checked timing.

The October paper's verified abstract supports testing PEA/TFE/IET and per-pixel calibration under controlled illumination; its application is MTF estimation. Its full experimental settings were not verified: [Idoughi and Hirakawa, 2026](https://pubmed.ncbi.nlm.nih.gov/42963707/). Model-specific interface/filter details are documented in [Prophesee timing interfaces](https://docs.prophesee.ai/stable/hw/manuals/timing_interfaces.html) and [event signal processing](https://docs.prophesee.ai/stable/hw/manuals/esp.html).

Previous campaign documents and JSON schedules remain as superseded historical planning records, not alternative instructions for this session. No additional pulse/PWM/intensity/fruit experiments are authorised by this plan.
