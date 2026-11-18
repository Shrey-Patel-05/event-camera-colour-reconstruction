# Offline audit of the original Arduino backup

15 November 2026. The supplied HEX and disassembly were read from disk. No
serial port, programmer or Arduino was contacted; neither input was changed.
The existing event-processing and colour-mapping algorithms remain unchanged.

## Main finding

**The firmware uses a 500 µs elapsed-time target for the entire ramp-up, then
a separate 500 µs elapsed-time target with all three outputs commanded zero.**
The 500 µs value is not a delay repeated at every brightness step.

It requests level 255 at the end of the ramp, then immediately starts clearing
all channels. There is **no programmed full-brightness hold and no ramp-down**.
Actual electrical/optical durations include software overhead and are not
measured by this audit.

## Input integrity and reproducibility

| Artifact | SHA-256 |
|---|---|
| `arduino_original_backup.hex` | `5db94ba5ccb05123a765252579955536c032fdc4a0ddc6a79d7e06813b32f752` |
| `arduino_original_disassembly.txt` | `6e0da82a0ceb3674618b779985bef84e5260cadf910adff17eb92907749922cc` |

All Intel HEX record checksums are valid: 1,024 data records and one EOF record
represent a contiguous 32,768-byte flash image. All 32,756 bytes explicitly
printed in the listing match that image; 12 flash bytes are not explicitly
printed in the listing. This is an internal artifact consistency check, not a
new readback comparison against the physical board. Flash data alone does not
establish fuse settings or actual oscillator frequency.

The audit script validates the inputs and packages address-specific evidence.
Its annotated function names are manual interpretations of instruction behaviour;
the original symbol names/source have not been recovered. It is neither a
general decompiler nor a cycle-accurate hardware simulator.

```bash
python3 audit_arduino_backup.py --output diagnostics/firmware_audit
python3 -m unittest discover -s tests -v
```

Use a new output directory on subsequent runs. Evidence and source-line-numbered
excerpts are in `diagnostics/firmware_audit/`. Nine repository tests pass,
including two tests that reject malformed HEX/checksum data and listing-byte
mismatches. The similarly named zero-byte file containing both filenames was
ignored and left untouched.

## Reconstructed command logic

The main loop at 0x0938–0x096e repeatedly calls the stage routine at 0x05e0 with
the three argument tuples below. The initialisation also commands all three
pins zero and performs a 1,000,000 µs clock-based startup wait at 0x0916–0x0932.

| Main call site | Selected channel tuple | Output pin |
|---|---|---|
| 0x0944 | (255, 0, 0) | D9 |
| 0x0954 | (0, 255, 0) | D10 |
| 0x0964 | (0, 0, 255) | D11 |

The physical R/G/B wiring is not established by these numeric tuples.

The following pseudocode explains the observed control flow. It is not the
original sketch, is not a new flashable programme and intentionally abstracts
the register/arithmetic helper implementations:

```text
all_channels_zero():
    analogWrite(D9, 0)
    analogWrite(D10, 0)
    analogWrite(D11, 0)

stage(selected_channel):
    all_channels_zero()
    start = micros()
    next_update = 0

    repeat:
        elapsed = unsigned(micros() - start)
        if elapsed >= 500:
            break
        if elapsed < next_update:
            continue

        level = floor(elapsed * 255 / 500)
        write_scaled_selected_channel(level)
        next_update = elapsed + 1

    write_scaled_selected_channel(255)
    all_channels_zero()
    dark_start = micros()
    while unsigned(micros() - dark_start) < 500:
        continue

after_initial_startup_wait:
    repeat:
        stage(D9)
        stage(D10)
        stage(D11)
        all_channels_zero()
```

For these calls the selected channel's maximum is 255, so its scaled request is
the computed `level`. Nonselected channels remain at the zero command. The
scaled-write function clamps levels to 0–255 and contains multiply/divide work.

There is no fixed loop of 255 equally spaced duty updates. Update eligibility
is `previous_sampled_elapsed + 1 µs`, but the clock granularity and execution
cost prevent interpreting this as a guaranteed 1 MHz update stream. An update
started below 500 µs can finish after that threshold before the next clock test.
Thus 500+500 µs is a nominal timer-test budget, not an exact measured 1,000 µs
stage duration; software clearing, arithmetic, calls, interrupts and transitions
add time. The corresponding nominal three-channel budget is 3 ms plus overhead.

## Addresses supporting the interpretation

| Address range | Evidence |
|---|---|
| 0x0500–0x051a | Zero requests for pins 9, 10, 11, in that order |
| 0x0536–0x05de | Clamp level, scale selected channel(s), divide by 255 and call analogWrite |
| 0x060a–0x061a | Clear outputs; sample/store start clock; initialise next-update threshold |
| 0x061c–0x0638 | Sample clock, subtract start, compare unsigned elapsed with 0x000001f4 = 500 |
| 0x0644–0x0658 | Multiply elapsed by 255 and divide by 500 |
| 0x065c–0x0674 | Write scaled channel level; advance eligibility threshold; return to clock test |
| 0x0676–0x0684 | Write level 255, then call the all-zero helper without a hold/wait between them |
| 0x0688–0x06a4 | Store a new clock origin, loop until a separate 500 µs has elapsed |
| 0x0916–0x0932 | Initial startup comparison against 0x000f4240 = 1,000,000 |
| 0x0938–0x096e | Fixed D9 → D10 → D11 stage calls and repetition |

The digital HIGH request at the end still has finite duration because further
instructions must run before the zero request reaches that pin. Clearing always
proceeds D9 → D10 → D11, so this software path need not give identical endpoint
pulse widths across channels. Their actual durations/optical effect were not
simulated or measured. The endpoint is a specific candidate to examine with a
scope/photodiode, not an established cause of the recorded event peaks.

## PWM and timebase configuration in this binary

The flash pin-to-timer table at 0x0068 contains codes 3, 4 and 7 for D9, D10 and
D11. The analogWrite branches identify these as Timer1 A, Timer1 B and Timer2 A.
The initialisation at 0x0834–0x0866 sets Timer1 divide-by-64 and the phase-correct
mode bit, and the corresponding divide-by-64/phase-correct bits for Timer2.
Under standard reset-state assumptions and the reported 16 MHz clock this is
consistent with 8-bit phase-correct PWM:

```text
T_PWM = 510 × 64 / 16,000,000 = 2.040 ms
f_PWM ≈ 490.196 Hz
```

The `micros`-like routine at 0x029c–0x02e4 reads Timer0 plus its overflow count
and scales by four. Under the standard clock its resolution is 4 µs. These
interpretations are supported by the
[Arduino timer implementation](https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring.c)
and [ATmega328P register definitions](https://github.com/avrdudes/avr-libc/blob/main/include/avr/iom328p.h).
The compiled code is consistent with these defaults; actual clock/optical
measurements remain separate work.

The analogWrite-like function at 0x01e4 contains distinct cases for values 0 and
255, which tail-call the digital-write routine with LOW and HIGH respectively.
Intermediate requests enable the relevant compare output and write its compare
register. This agrees with the
[Arduino analogWrite implementation](https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring_analog.c).

Consequently, a 500 µs ramp-up spans less than one nominal PWM period, and its
electrical output need not be a gradual brightness envelope. D9/D10 share one
timer while D11 uses another; equal carrier frequency alone does not establish
equal phase. Driver polarity, current regulation and optical response are still
unknown. We cannot conclude from this code alone how many useful optical pulses
occurred or which event burst corresponds to physical light onset.

UART infrastructure is present, but the active main loop contains no identified
duration/brightness command parser. Linked serial routines do not establish an
existing runtime control interface. This supports keeping the adjustable
duration/drive matrix deferred rather than assuming the board can accept new
settings through serial messages.

## Consequences for the next recordings

1. Preserve the binary and use its SHA-256 in every new run manifest. The
   fixed-firmware protocol can now name the command ramp/dark targets as audited
   values while keeping measured electrical/optical durations empty until observed.
2. Identify physical pin colours and driver polarity, then observe the three
   outputs together if lab instrumentation is available. Inspect both the
   sub-period PWM behaviour and the final 255-to-zero transition.
3. Keep the first reference/uniform-target takes at unchanged firmware and
   camera configuration. Optical attenuation remains a separate optional test.
4. Do not configure old files to a 3 ms RGB cycle on this evidence. No provenance
   links this exact binary to all historical DATs, and 3 ms is only the nominal
   command budget before overhead, not an optical timing measurement.
5. Keep the current detector and original 1/10/100 ms comparison intact. Once
   new waveforms and their camera-clock relation are measured, evaluate an
   explicitly separate timing model against that reference.
