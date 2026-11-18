> **Superseded for the 16 November session:** use [the final 21-recording plan](recording_plan_2026-11-16.md), [checklist](recording_checklist_2026-11-16.md) and [firmware instructions](../arduino/README.md). This document is a historical planning record; its fixed-firmware restrictions and extra experiment lists are not the active session scope.

# Immediate campaign with the original Uno firmware preserved

Updated 15 November 2026 after the [offline firmware audit](arduino_firmware_audit.md). This
document supersedes the adjustable LED duration/drive instructions for the
immediate session. No firmware upload, timer change, circuit rewiring, new
controller logging or new marker waveform is authorised on the existing board.
This work changes local planning artifacts only; no board was contacted.

## Known, reported and unresolved

| Item | Current evidence |
|---|---|
| Controller | User reports Arduino Uno / ATmega328P, standard 16 MHz clock |
| Firmware | HEX and disassembly are available locally, internally validated and hashed; original source unavailable |
| LED control pins | Binary confirms D9 → D10 → D11 stages; physical pin-to-colour mapping still needs documentation |
| Brightness implementation | Binary confirms analogWrite-style intermediate PWM and digital endpoints |
| Timing | Binary confirms a 500 µs elapsed-time ramp-up target, no explicit peak hold/ramp-down, then a separate 500 µs zero-command wait |
| Exact interpretation | Whole-ramp timing test, not a per-step 500 µs delay; software overhead/loop overrun and actual optical response remain unmeasured |
| Circuit | Driver/LED board, polarity and wiring not yet identified |
| Instruments | Scope/logic analyser/photodiode availability not yet established |
| Local artifact access | `arduino_original_backup.hex` and `arduino_original_disassembly.txt` in the reconstruction repository; see audit for hashes and instruction addresses |
| Historical recordings | No firmware-to-DAT provenance establishes that this exact binary produced every earlier 1/10/100 ms file |

Keep the HEX and disassembly intact and record their hashes in the session
manifest. A generic Arduino core is a reference
for the audit, not proof of the linked core version or timer state in this binary.

## Why the PWM detail matters

With the standard Arduino AVR configuration, D9/D10 use Timer1 A/B and D11 uses
Timer2 A. Timer1 and Timer2 default to 8-bit phase-correct PWM with divide-by-64
prescaling. At 16 MHz the nominal period is:

```text
T_PWM = 510 × 64 / 16,000,000 = 0.002040 s = 2.040 ms
f_PWM ≈ 490.196 Hz
```

Sources: [official Uno pin/timer mapping](https://github.com/arduino/ArduinoCore-avr/blob/master/variants/standard/pins_arduino.h)
and [Arduino AVR timer initialisation](https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring.c).

The audited whole-ramp elapsed-time target of 500 µs occupies about 0.245 of a nominal PWM
period. Rapidly changing duty does not automatically create a smooth optical
fade. Emitted pulses can depend on timer phase and compare updates. This is a
plausible mechanism to investigate, not a measured optical waveform or a proved
explanation of the historical bands/100 ms event recurrence.

Two details constrain the interpretation:

- D9/D10 share a timer while D11 uses another. Equal nominal frequencies do not
  establish matched phase across all three outputs.
- Standard analogWrite handles values 0 and 255 as fixed digital LOW/HIGH,
  rather than intermediate-duty PWM. Ramp endpoints can therefore behave
  differently. The unknown LED driver determines how pin polarity translates
  into optical output. See the
  [official analogWrite implementation](https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring_analog.c).

The audit confirms initialisation consistent with these defaults. Actual clock,
electrical period, PWM phase and LED waveform still need measurement. The final
255 request immediately followed by zero commands is particularly worth observing.

## First experiment: characterise the existing controller

The immediate independent variable is the observation/scene or a documented
external optical condition, with the controller programme held unchanged.
The question is: does its emitted sequence provide repeatable, colour-labelled
stimuli suitable for the current ROI features?

### Read-only firmware audit — completed for the supplied backup

The [audit report](arduino_firmware_audit.md) documents the reconstructed command
loop, timing constants and timer paths. Its remaining measurement checklist is:

1. Map the confirmed D9 → D10 → D11 sequence to physical LED colours.
2. Measure actual duty-update/electrical output and per-stage/cycle durations.
3. Measure optical rise/fall, endpoint behaviour and zero-command recovery.
4. Verify the actual clock/carrier period and inter-timer phase relationship.
5. Keep the original controller fixed: no duration/brightness command parser
   was identified in the active loop. Do not send serial commands to discover one.

Static analysis gives a command-timing model under explicit assumptions. It
does not measure LED light, driver delays, supply variation or the relation
between controller and camera clocks.

### Electrical and optical observations, if instruments are available

Identify the circuit and use suitable high-impedance probes to observe D9,
D10 and D11 together. Capture a long overview covering multiple complete
programme repeats and a close view resolving individual PWM pulses. Save numeric
waveforms and sample-rate/timebase metadata. Include a photodiode trace in the
same acquisition where possible to compare electrical and optical behaviour.

This can establish actual carrier period, burst/duty evolution, channel order,
dark recovery and repeat-to-repeat changes without reflashing. Record which
part of the circuit was probed and its polarity. A logic waveform alone does
not establish optical intensity or that the LED switches instantly.

The current PWM pins are not newly generated clean stage gates. Do not label
every electrical PWM edge as a new colour-stage onset. An inactive/gated channel
can also be ambiguous if the driver polarity is unknown.

To obtain a camera-clock reference without changing firmware, an available
external reference must be observed by both the measurement equipment and the
camera's correctly configured Trigger In. Merely starting a scope and a camera
at roughly the same time does not synchronise their clocks. Without a shared
reference, mark the camera/trace relationship as unverified or estimate alignment
with stated uncertainty; do not export event-derived phase as hardware truth.

If instruments are unavailable, collect useful raw events and reference targets
but label them as a fixed-firmware characterisation dataset with unverified
optical timing. A conventional video can document the scene; it does not resolve
500 µs timing unless its acquisition genuinely supports that measurement.

## Captures possible without changing the programme

1. **Nominal reference scene, three separate takes.** Include matte white, gray,
   black and labelled colour patches; fix camera, ambient light, biases and
   target placement. Retain RAW and complete configuration. Choose the clip
   duration after measuring/estimating the actual repetition period. Aim for
   100 complete repeats where practical, but keep measured counts distinct from
   targets while the period is unresolved. Do not impose a nominal cycle in the
   counting merely to reach 100.
2. **Uniform matte gray/white target, three takes.** Keep the camera and controller
   unchanged. This makes row/band structure easier to compare without the ball's
   sectors. Its cause remains an experimental question.
3. **Baseline light control.** If an existing optical shutter/cover can exclude
   the experimental LED illumination while preserving ambient conditions, record
   the static target under that condition. Label residual leakage. This differs
   from proving that the controller is electrically commanding all channels off.
   Constant single-channel illumination is unavailable unless already supported.
4. **Optional optical attenuation, three levels × three takes.** Only if suitable
   existing optics are available, attenuate the illumination path with unchanged
   geometry/timing and log filter identity, placement and spectral information.
   This tests optical loading while leaving programmed PWM intact. An unknown
   filter cannot be claimed to preserve RGB ratios or to provide calibrated
   low/middle/high optical powers. Do not change supply voltage or LED current
   with an unidentified driver.
5. **Additional target layouts/instances at the nominal setting.** Preserve
   three held-out layouts/physical sample groups for subsequent model evaluation;
   save separate ROIs/reference photos. Do this after the reference scene's
   acquisition is usable.

The nominal reference condition in the optional attenuation block can reuse
the first three nominal takes if configuration/geometry are identical. If no
attenuation optics exist, those six extra takes stay deferred; repeated
identical files are not a brightness experiment.

Changing camera aperture is a separate camera-optics experiment: it affects
ambient light and potentially depth of field as well as received LED light.
It should not be relabelled as an LED brightness change. Camera bias or filter
sweeps are separate blocks after a fixed-config reference has been recorded.

## What remains deferred

The earlier 27-take on-duration × drive matrix, square-pulse sequence, programmed
first-colour preamble, different dark gaps, steady single-colour controls and
new per-stage log/trigger signals require capabilities not yet established in
the unchanged firmware. Preserve that proposal as a future controlled-generator
experiment. It cannot be executed merely by recording longer clips, choosing
different playback windows or changing filename durations.

No action to reflash the existing board is part of this plan. A later separately
authorised controllable setup could implement the full matrix while keeping
the original controller available as a baseline.

## Before leaving the session

- RAW files reopen and native timestamps/settings are saved; technical problems
  are checked immediately rather than after the apparatus is dismantled.
- Every run links to the exact firmware backup hash, scene and optical condition.
- Pin-to-colour, electrical polarity, nominal timer settings and measured
  waveform facts are labelled separately from assumptions.
- Reference ROIs show sufficient measurable activity for feature analysis;
  single-event normalisation is explicitly flagged. Weak black/absorbing targets
  are retained rather than forced to respond.
- Global/ROI ON/OFF traces and row-count maps are checked, and all available
  instrument traces and clock references are retained.
- Repeatability failures are retained as scientific outcomes; missing files,
  truncated captures and unlogged configurations receive technical retakes.
- The saved metadata does not claim measured LED onsets, true RGB identity or
  a hardware timing reference where only a software/event-derived estimate exists.

These recordings can support reproducibility, optical-load and ROI-feature
studies with the existing controller. A controlled illumination-duration study
and supervised synchronisation benchmark still require independently established
timings and genuinely adjustable or separately verified stimulus conditions.
