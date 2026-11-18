# Offline firmware verification — 16 November 2026

Updated after the user-approved reconstructed legacy amendment. One recording_session sketch now implements all 21 recordings, including `RUN L1` / `RUN L2`. No serial port, camera or Arduino was contacted; no upload, restoration or optical measurement was performed.

## Compiler checks

Arduino CLI 1.6.0 compiled `arduino/recording_session` for `arduino:avr:uno` with warnings enabled, installed AVR core 1.8.6 and AVR GCC 7.3.0.

| Build | Flash | Global SRAM | Result |
|---|---:|---:|---|
| Existing local active-HIGH, hardware-confirmed configuration | 7668 / 32256 bytes | 316 / 2048 bytes | Passed, includes reconstructed L and all digital modes |
| Confirmation disabled via compiler definition | 3104 / 32256 bytes | 308 / 2048 bytes | Passed; pins remain inputs, RUN rejected |
| Active-LOW via compiler definition, confirmation enabled | 6068 / 32256 bytes | 316 / 2048 bytes | Passed; digital modes supported, audited active-HIGH legacy mode rejected |

The local hardware configuration was already set to confirmed/active-HIGH when this amendment began. That file was left byte-for-byte unchanged. Compilation does not independently confirm physical current limits or optical output. The legacy implementation targets the 16 MHz ATmega328P and rejects other AVR CPU/clock targets at compile time.

## Test results

`python3 -m unittest discover -s tests -v`: **25 tests passed**, including all **16 recording-session tests** and the existing audit/decoder/ROI/comparison tests.

The session tests compile the actual firmware with simulated Arduino I/O under C++11, warnings treated as errors. They cover:

- Exactly 21 run IDs, including two independent reconstructed-legacy commands.
- Saved design/header/J-table consistency and all 57 nonlegacy run/profile timeline combinations.
- A regression fixture captured before this amendment confirms every existing digital command CSV remains byte-for-byte unchanged.
- J seeds, balanced intended colour identities, variable gaps and exact omission counts.
- Existing digital command parsing, no-flash controls, expected edge counts, final OFF, active-LOW operation, clock wraparound and late-deadline aborts.
- Direct legacy-stage command/clock traces for each of D9/D10/D11, including wraparound: ordered all-zero calls; brightness `floor(elapsed * 255 / 500)` only before 500 microseconds; selected-channel-only updates; explicit 255 endpoint; immediate D9/D10/D11 zero calls with no sampled hold/ramp-down; separate dark wait of at least 500 microseconds.
- Legacy intermediate analogWrite requests occur with Timer1/Timer2 phase-correct /64 settings; zero/255 follow the simulated Arduino digital endpoint paths. This checks requested configuration, not actual carrier pulses.
- Full L1/L2 runs have no marker, one-second startup, at least five seconds of measurement, complete RGB cycles, correct RGB endpoint order, all-off completion and restored timer control/output-compare registers.
- Rejected unconfirmed/incompatible legacy configurations and successful digital commands after legacy runs in the same boot.
- L metadata/JSON recipes explicitly identify reconstructed original firmware and do not fabricate absolute optical/GPIO edge tables.
- Optional serial logger accepts a legacy recipe and preserves identity/controller reports using a simulated port; no real port is opened by the tests.
- Prepared bundles preserve unresolved C selection and refuse directory overwrites.

Both Python helpers pass bytecode compilation. Representative selected-T2 bundle generation was also inspected: 21 rows, usable L1/L2 commands, recipe JSON, minimum-duration labels and unchanged digital schedules. The real serial logger/camera workflow remains untested against physical hardware.

## Reconstruction evidence and limitations

The preserved [audit](arduino_firmware_audit.md) and disassembly establish: ordered all-zero helper at 0x0500–0x051a; clamp/selected-component scaling at 0x0536–0x05de; ramp/update/endpoint/dark logic at 0x05e0–0x06a4; one-second startup at 0x0916–0x0932; and D9/D10/D11 repetition at 0x0938–0x096e. The implementation follows those rules, including skipping nonselected components during ramp updates.

Timer configuration matches the audited standard-clock interpretation: Timer1 A/B and Timer2 A, 8-bit phase-correct PWM, /64 prescaler, nominal 2.040 ms carrier period. Installed core analogWrite uses hardware PWM for 1–254 and digital endpoints for 0/255. Counter phase is neither reset nor synchronised; its relationship in the original system was not established.

The original loop was continuous. The new wrapper adds serial selection, repeats startup per RUN, and stops after a complete RGB cycle once five seconds have elapsed. Source compilation, call/core overhead, PWM phase and optical dynamics differ from the original binary. Tests verify source/control-flow correspondence and logical operations, not cycle-accurate AVR execution or measured optical equivalence. Legacy reporting therefore gives actual controller elapsed time and completed cycles, rather than the digital modes' deadline-jitter/edge statistics.

## Preserved files

Original backup hashes remain:

- HEX: `5db94ba5ccb05123a765252579955536c032fdc4a0ddc6a79d7e06813b32f752`
- Disassembly: `6e0da82a0ceb3674618b779985bef84e5260cadf910adff17eb92907749922cc`

Existing analysis-code edits were present before this task and were left untouched. Both J realised tables and the existing hardware_config.h were also checked against pre-amendment hashes. Historical recordings/results were unchanged. The plan/checklist now use reconstructed L1/L2 directly; original-HEX restoration is outside this requested workflow.

## Remaining physical validation

Compile/simulation results do not establish actual LED current, emitted waveform, GPIO jitter, capture throughput or camera/controller clock alignment. Preserve the reconstructed identity in analysis and do not interpret the nominal 500/500 microsecond targets or 3 ms RGB budget as verified optical timestamps. All 21 modes are selectable in the same sketch; capture failures, insufficient lab time or no usable T1–T3 remain practical constraints.
