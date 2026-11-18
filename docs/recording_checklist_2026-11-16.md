# Lab checklist — 21 recordings, 16 November 2026

Use the [final plan](recording_plan_2026-11-16.md) and [firmware instructions](../arduino/README.md). Record every agreed ID once; restart camera acquisition for each independent take. Mark failed/missing runs explicitly. Technical retakes retain the original file and use a suffix/reason.

## Before the session

- [ ] Bring labelled physical matte swatches, ball, fixed white/grey patches, mounting materials and layout map.
- [ ] Bring fishing line/string and a small separate object. Establish the route through the existing opening; mark parked position/path away from sample ROIs.
- [ ] Use this sketch for all 21 IDs. L1/L2 are now the user-approved **reconstructed original firmware**, not the preserved binary. Retain the original HEX/disassembly as evidence; no restoration is part of this session.
- [ ] Inspect the physical pin-to-colour map, LED-on polarity, driver/current and ability to support the new finite full-drive pulses, including the 80 ms marker.
- [ ] Check the existing hardware_config.h settings and compile the updated Uno sketch. Archive final source, HEX and hashes. Prepare a fresh screen bundle; check both L recipe JSON files and realised J tables are present. Old bundles have an obsolete design hash.
- [ ] Prepare capture folders, free disk space and a second-copy destination. Optional Python logger requires pyserial; otherwise plan to save the serial transcript manually.

## Set up once

- [ ] Upload the updated unified sketch when ready, then open Serial Monitor at 115200 baud with newline line endings. Save READY/INFO and check design hash, RGB pins, polarity and confirmation flag. L and all other runs use this build.
- [ ] Record actual camera model/serial, acquisition version, lens/focus/aperture, resolution, biases, filters and ERC settings. Save settings file and setup photo.
- [ ] Fix camera, LEDs, ball, samples and reference patches. Keep room light and box opening state constant. Set line/object up now and park it for L–J.
- [ ] Photograph layout A with sample IDs. Exclude text/borders from later ROIs. Retain the samples for future reference-colour measurement.
- [ ] Preview event rate, polarity and sample visibility. Check filter/drop indicators. Confirm enough event detail remains for PEA/TFE/IET.
- [ ] If existing trigger/photodiode equipment is available, verify the exact interface and saved timestamp stream. Otherwise mark timing as command/event-derived and optical timing unverified. No new trigger wire is driven by this firmware.

## Run sheet

The selected condition is **C = ____ (T1/T2/T3)**. Reason: ____________________.
Use that same choice for every dependent command below; the examples use `<C>` as a placeholder.

| Done | Run | Scene/action | Firmware command | Event file / note |
|---|---|---|---|---|
| [ ] | L1 | A; stationary; reconstructed legacy, 1 s dark + at least 5 s RGB | `RUN L1` | |
| [ ] | L2 | A; new independent capture; same reconstructed legacy | `RUN L2` | |
| [ ] | N1 | A; stationary, LEDs off | `RUN N1` | |
| [ ] | N2 | A; stationary, LEDs off | `RUN N2` | |
| [ ] | SR | A; red-only measurement, 10/20 ms | `RUN SR` | |
| [ ] | SG | A; green-only measurement, 10/20 ms | `RUN SG` | |
| [ ] | SB | A; blue-only measurement, 10/20 ms | `RUN SB` | |
| [ ] | T1 | A; RGB 1/0.5 ms | `RUN T1` | |
| [ ] | T2 | A; RGB 1/5 ms | `RUN T2` | |
| [ ] | T3 | A; RGB 5/5 ms | `RUN T3` | |
| [ ] | CA1 | A; stationary | `RUN CA1 <C>` | |
| [ ] | CA2 | A; new independent capture | `RUN CA2 <C>` | |
| [ ] | CA3 | A; new independent capture | `RUN CA3 <C>` | |
| [ ] | CB1 | B; samples moved, new map photographed | `RUN CB1 <C>` | |
| [ ] | CB2 | B; new independent capture | `RUN CB2 <C>` | |
| [ ] | D | Restore A; photograph restored map | `RUN D <C>` | |
| [ ] | J1 | A restored; no motion | `RUN J1 <C>` | |
| [ ] | J2 | A restored; different saved sequence | `RUN J2 <C>` | |
| [ ] | M1 | A restored; LEDs off; separate object moving | `RUN M1` | |
| [ ] | M2 | A restored; flashing; separate object parked | `RUN M2 <C>` | |
| [ ] | M3 | A restored; same flashes; separate object moving | `RUN M3 <C>` | |

## Transition points

- [ ] **After L2:** continue directly with `RUN N1` and `RUN N2` in the same uploaded sketch. No firmware switch is needed. Keep geometry/settings unchanged; preserve each L DONE report and reconstructed-firmware label.
- [ ] **After T3:** inspect the three recordings/reference responses and select one T profile. Record evidence. If none works, flag the constraint and discuss revision; do not silently introduce a fallback or extra experiment.
- [ ] Prepare a new bundle with `--selected T1`, T2 or T3. Preserve the screen bundle's completed metadata. Copy the compiled HEX hash and settings/layout references into applicable metadata records.
- [ ] **Before CB1:** move individual swatches between image positions. Keep white/grey references, ball, camera and LEDs fixed. Save layout B map.
- [ ] **Before D:** restore original positions; save restored layout map and any differences.
- [ ] **Before M1:** verify the same opening/line route and stationary samples. Move only the separate object. For M1/M3, start moving before measurement and continue until DONE; for M2, document the parked position.

## For every new-firmware take

1. Verify run ID, layout, movement state, selected profile and prepared schedule. Firmware cannot check physical sample positions.
2. Start a **fresh camera recording**, then send the exact command. With the logger, press Enter only after camera capture starts. Do not type more commands during execution.
3. Preserve context and measurement through DONE. L1/L2 have no RGB marker: 1-second dark startup then at least 5 seconds of reconstructed ramps, finishing the final RGB cycle. N/M1 have no optical marker and remain off for 7 seconds. Digital flashing runs include the marker; S measurement itself is single-colour.
4. Stop/save camera capture after DONE plus a little margin. Save raw event polarity/timestamps and any native RAW/derived DAT, trigger stream and conversion settings. Keep all files even if scientific responses are weak.
5. Save INFO/START/DONE or ABORTED transcript; link event filename to metadata. DONE confirms controller execution only. Inspect file readability, timestamps/event duration, ON/OFF presence, target coverage and drop indicators. Flag ABORTED/incomplete captures before deciding a documented retake.

## Before leaving

- [ ] Count the 21 IDs and identify missing/incomplete ones. No additional experiments are added to fill time or replace failures.
- [ ] Confirm C-A/C-B/D/M2/M3 share exactly the selected T schedule. J1/J2 use their correct distinct realised tables and selected ON width.
- [ ] Preserve digital command CSVs, L1/L2 elapsed-time recipe JSON, source/compiled HEX hashes, serial reports and settings with raw files. Verify both L records say reconstructed original firmware, not exact binary reproduction. Host timestamps and controller origins remain labelled as separate clocks.
- [ ] Save sample maps/photos and movement-path notes. Keep physical swatches for later CIELAB reference measurement.
- [ ] Verify a second copy and record its location.

## Constraints to flag promptly

L run rejected due to incompatible pin mapping/polarity; unknown driver/current limits; no usable T1–T3; excessive event drops or disk load; inadequate motion route; missing settings/file provenance; insufficient time for 21 independent recordings. Missing optical timing instrumentation limits claims about synchronisation/TFE. Missing measured swatch colours limits absolute CIELAB accuracy. Neither should be disguised as a completed calibration.

The previous 30–60 minute allocation is superseded. With prepared equipment these are short captures, but upload, screening, rearrangement and verification take time. Reserve enough session time and report any uncompleted agreed IDs.
