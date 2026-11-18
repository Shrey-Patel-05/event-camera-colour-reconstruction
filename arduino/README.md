# Selectable firmware for the 21-recording session

Target: Arduino Uno / ATmega328P, standard 16 MHz board. See the [agreed plan](../docs/recording_plan_2026-11-16.md) and [lab checklist](../docs/recording_checklist_2026-11-16.md). One build serves all 21 recordings, including reconstructed legacy L1/L2, S, T1/T2/T3, C, D, J, M and LEDs-off N. It starts idle, runs one finite block on command, then returns to all-off. L uses the audited PWM ramp; all other illumination modes retain their digital sequences. No serial logging occurs during illumination.

## Before building for hardware

The user has explicitly selected a source reconstruction for L1/L2 after replacing the original installed application. Use `RUN L1` and `RUN L2` in this same sketch; no original-HEX restoration is required for this plan. Label them **reconstructed original firmware**, with `exact_binary_reproduction=false`. The original backup and disassembly remain preserved evidence.

Edit [hardware_config.h](recording_session/hardware_config.h) after checking the physical circuit:

- `LED_PINS` is in user-confirmed physical R/G/B order: `{9,10,11}`.
- The user confirmed `COMMON_ANODE=false` (common cathode), matching `RECORDING_LED_ACTIVE_HIGH=true`: HIGH is on and LOW is off.
- Confirm the existing driver, resistors and full-drive current support the pulses, including the 80 ms blue start marker. Only one channel is commanded active at a time.
- `RECORDING_HARDWARE_CONFIRMED` controls whether RUN can drive the LEDs. Its existing local setting is preserved by this change. A build with it set to `false` leaves LED pins as inputs and rejects RUN. L additionally requires the confirmed D9/D10/D11, active-HIGH configuration; it does not invent a polarity-inverted version of the audited programme.

The sketch does not generate a hardware Trigger In output. Trigger wiring is deferred until the exact interface/cable and electrical compatibility are known. The optical start pattern is useful for alignment, with uncertain optical delay and event-derived phase.

## Build offline

The canonical design is [session_2026-11-16.json](../experiments/session_2026-11-16.json). The generated header stores both exact realised J tables in flash, avoiding a different PRNG implementation on the Uno.

```sh
python3 tools/prepare_recording_session.py generate --check
arduino-cli compile --fqbn arduino:avr:uno --output-dir /tmp/recording-session-build arduino/recording_session
```

On this Mac, if arduino-cli is not in PATH:

```sh
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn arduino:avr:uno --output-dir /tmp/recording-session-build arduino/recording_session
```

AVR core 1.8.6 and its toolchain are installed locally. To edit design data, regenerate with `python3 tools/prepare_recording_session.py generate`, inspect changes, then recompile. Do not hand-edit the generated header. Use Arduino IDE for a later upload after hardware verification; L1/L2 run from this same build. Select Arduino Uno and the actual board port. Compilation does not upload; neither command above contacts a serial device.

Archive the application `.hex` (without bootloader), its SHA-256, the hardware configuration and source files used for the final build. Record that build hash in each metadata file. The printed design hash identifies schedule data; it does not certify wiring or identify every compiled binary. Reprepare bundles if hardware configuration/source changes after the snapshots were made.

## Prepare schedule and metadata bundles

Before T screening, use a fresh output directory:

```sh
python3 tools/prepare_recording_session.py prepare --output recordings/2026-11-16/screen
```

After selecting T1/T2/T3, prepare a NEW bundle. Example only, if T2 was selected:

```sh
python3 tools/prepare_recording_session.py prepare --selected T2 --output recordings/2026-11-16/selected_T2
```

Preparation never opens a serial port and refuses to overwrite an existing directory. It creates a 21-row run sheet, per-run metadata, design/source hashes, a firmware source snapshot and full command schedules for resolved conditions. Without `--selected`, C/D/J/M2/M3 remain explicitly unresolved. Keep the screen bundle with the recordings already taken; use the selected bundle only for subsequent IDs. Duplicate **templates** in the second bundle are not additional recordings. Do not overwrite metadata filled during screening.

Each CSV includes pre-dark, preamble, settle, measurement and post-dark phases. Time origin is the controller's `run_origin_us`, sampled after START output has finished. For pulse rows, `target_on_us`/`target_off_us` are requested edge deadlines and `slot_end_us` includes the following gap. An `omitted=1` row has an intended colour but **no LED edges**. Idle rows (`colour=-`) remain all-off; their time columns describe the dark interval, not a pulse. L exports a JSON elapsed-time recipe rather than an invented absolute edge schedule.

J gap multipliers/omissions and channel identities are also committed as `experiments/irregular_2026-11-16_J1.csv` and `J2.csv`; selected ON width/base gap determine their final timestamp tables. Seeds alone are not the only record.

## Operate one take

Open a single serial connection at **115200 baud**, newline line ending. Opening the Uno USB serial connection may reset it; it comes back idle and requires another explicit command. Close Arduino Serial Monitor before using the optional Python logger. Do not send additional characters during a run: they can cause receive interrupts and queue another command. A running finite block does not poll serial for an abort; a hardware reset interrupts it. Preserve interrupted takes as incomplete.

`INFO` prints the design hash, configured RGB pins, polarity and confirmation flag. Valid RUN commands:

| Recording | Command |
|---|---|
| L1/L2, reconstructed original | `RUN L1` / `RUN L2` (no T argument) |
| N1/N2 | `RUN N1` / `RUN N2` |
| S red/green/blue | `RUN SR` / `RUN SG` / `RUN SB` |
| T1/T2/T3 | `RUN T1` / `RUN T2` / `RUN T3` |
| C-A takes | `RUN CA1 T2`, `RUN CA2 T2`, `RUN CA3 T2` if T2 selected |
| C-B takes | `RUN CB1 T2`, `RUN CB2 T2` if T2 selected |
| D | `RUN D T2` if T2 selected |
| J | `RUN J1 T2`, `RUN J2 T2` if T2 selected |
| M1 | `RUN M1` |
| M2/M3 | `RUN M2 T2`, `RUN M3 T2` if T2 selected |

Replace T2 consistently with the one selected profile. Dependent RUN commands require an explicit profile every time; it is not stored in EEPROM or silently remembered across resets. Independent runs reject an extra T argument. IDs are case sensitive. Unknown IDs and malformed commands are rejected. Firmware does not know physical layouts or object motion: the operator must match the run sheet.

Start a fresh camera recording **before** RUN. Capture through DONE, then stop/save. Preserve the serial INFO/START/DONE transcript alongside the event file. N/M1 contain no start flashes and stay off for 7 seconds total. Digital flashing conditions have R20/G40/B80 ms start pulses, each followed by 20 ms dark, then 500 ms dark settling. S measurement itself remains single-colour. Exclude marker and settling phases from colour features. L1/L2 have no RGB marker or added settling sequence: one second all-zero startup, then at least five seconds of reconstructed RGB ramp stages, stopping after a complete RGB cycle and returning OFF.

Optional logger, requiring `pyserial` in the chosen Python environment:

```sh
python3 tools/capture_arduino_run.py --bundle recordings/2026-11-16/selected_T2 --run CA1 --port /dev/cu.YOUR_UNO_PORT
```

Use the actual known board port; this is not an executable placeholder. The helper opens the board, checks the design hash/hardware flag, asks you to start the separate camera acquisition, then sends the prepared command and saves a JSONL serial transcript. It updates controller status but never claims that the camera file was captured correctly. Fill camera paths/settings and quality fields afterwards. An already attempted ID is refused to protect its record. A retake uses a fresh bundle and a documented capture filename suffix/reason.

## Timing behaviour and reports

For digital modes, absolute, wrap-safe micros deadlines retain the intended cadence rather than accumulating a per-stage delay call error. Standard Uno micros quantisation is 4 microseconds. GPIO-call overhead, interrupts, oscillator error and optical dynamics still affect actual edges. Off always means all RGB off; at most one is commanded active.

For digital modes, DONE/ABORTED reports run ID, controller origin, planned cursor, completion elapsed time, maximum observed software lateness, count of GPIO operations observed over 20 microseconds late, and emitted-edge count. An operation over 100 microseconds overdue before execution aborts the block to all-off. These are aggregate software observations, not a saved timestamp for every physical GPIO/optical edge. On ABORTED, `planned_end_us` is the last cursor reached, not the full scheduled duration; use the CSV for the full intended timeline.

There is no serial traffic generated in the time-sensitive loop. Schedule export is done offline, so it cannot introduce gaps inside T/C/M. Complete schedules, controller reports and event-derived start alignment do not independently verify light output or camera/controller clock correspondence. Use a suitable independently measured subset before claiming absolute TFE or supervised timing accuracy.

## Reconstructed original mode: L1/L2

`RUN L1` and `RUN L2` execute the same waveform logic in separate finite takes. Each stage clears all channels with analogWrite zero in D9/D10/D11 order, records its micros origin, then requests `floor(elapsed_us * 255 / 500)` while elapsed time is below 500 microseconds. Next-update eligibility is the previous sampled elapsed time plus 1 microsecond; it is not a 1 MHz update guarantee or a loop over 255 equally spaced steps. The scaled-write routine updates only nonzero components of the selected RGB tuple, matching disassembly at 0x0536–0x05de.

At the ramp endpoint, the code requests 255, immediately clears all channels in the audited order, then waits a separate 500-microsecond all-zero interval measured after clearing. There is no programmed peak hold and no ramp-down. Repetition is `(255,0,0)` -> `(0,255,0)` -> `(0,0,255)`, then another all-zero clear, as at 0x0938–0x096e. The audited one-second startup wait is included once per commanded run.

Timer1 (D9/OC1A, D10/OC1B) and Timer2 (D11/OC2A) use 8-bit phase-correct PWM with divide-by-64 prescaling. Under the Uno's nominal 16 MHz clock, carrier period is 2040 microseconds, about 490.196 Hz. Values 1–254 use Arduino AVR analogWrite PWM; 0 and 255 use its LOW/HIGH digital endpoint paths. Timer counters/prescalers are not reset/synchronised; their relative phase is not established by the audit. Control registers and output-compare values are restored after clearing outputs so subsequent digital modes retain their prior timer configuration.

The original main loop was continuous. The recording wrapper instead runs for at least five seconds, completing the final RGB cycle before stopping OFF. It adds the serial interface and finite termination but no start marker, no 500 ms settling block, and no post-dark delay. `START`/`DONE` identify `firmware_identity=reconstructed_original_firmware` and `exact_binary_reproduction=0`. DONE gives actual completed RGB-cycle/stage counts and controller measurement/start/completion times; it does not fabricate optical edge counts or digital deadline-jitter statistics.

The recipe files `L1_schedule.json` and `L2_schedule.json` record these rules, the audit/backup reference, PWM configuration and reconstruction limitations. The nominal six-second total is a minimum plus cycle completion and software overhead. Actual update samples, execution overhead, timer phase and optical output are not equivalent to the original binary. Even if two takes give similar event plots, label them as reconstructions. Prepare fresh bundles after this update so their design hash matches the new firmware; the optional serial logger supports both legacy recipes and digital CSV schedules.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_recording_session.py' -v
```

Tests compare host-exported timelines with the shared C++ scheduler for all resolved run/profile combinations, validate J omissions and grouping, and exercise the actual firmware command/output logic with simulated Arduino I/O. Compile the Uno build as well: a desktop simulation does not verify optical output or real interrupt timing. Offline results are recorded in [firmware validation](../docs/recording_firmware_validation_2026-11-16.md).
