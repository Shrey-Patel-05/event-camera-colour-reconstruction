# Simple RGB hardware tests

Open **arduino_hardware_tests.ino** in Arduino IDE, select Arduino Uno, and change only the `#define TEST_MODE 1` line to select a test. All test functions, pins, durations and repetition counts are inside that single sketch. There are no extra libraries/configuration files. This sketch is separate from the 21-recording firmware and does not change its confirmation flag.

**Before uploading:** uploading replaces the currently installed application. The current recording plan uses user-approved reconstructed L1/L2 modes inside [recording_session.ino](../recording_session/recording_session.ino); no original-HEX restoration is required. This hardware-test sketch remains separate and has only been compiled/simulated by the coding agent.

## Modes and defaults

Every mode starts with all outputs OFF and waits 2 seconds. Tests start automatically; no Serial Monitor command is needed. Serial Monitor at **115200 baud** identifies the selected mode and reports completion.

| TEST_MODE | Behaviour after startup |
|---:|---|
| 0 | Remain OFF indefinitely |
| 1 | Red D9: five flashes, 100 ms ON / 900 ms OFF |
| 2 | Green D10: five flashes, 100 ms ON / 900 ms OFF |
| 3 | Blue D11: five flashes, 100 ms ON / 900 ms OFF |
| 4 | Five RGB cycles; each colour 100 ms ON / 900 ms all-OFF |
| 5 | 500 RGB cycles; each colour 1 ms ON / 0.5 ms all-OFF, about 2.25 seconds |
| 6 | 100 RGB cycles; each colour 5 ms ON / 5 ms all-OFF, about 3 seconds |

After completion, the sketch keeps all three LEDs OFF. Press reset or power-cycle to repeat. Opening Serial Monitor may reset the Uno and repeat the test automatically. Fast flashes may look steady or mixed to your eyes, despite only one channel being commanded active at any instant. Use modes 1–4 to check colour mapping visually.

Durations and repeat counts are grouped at the top. Messages for modes 5/6 describe their default timing; if you change those constants, use the actual constants as the timing reference. Timings are nominal delays plus GPIO/function/interrupt overhead, suitable for hardware checks rather than precise optical calibration. Short microsecond delays are compile-checked to stay within 1–16000 microseconds.

## Wiring and conservative operation

Confirmed mapping: red D9, green D10, blue D11, common cathode (`COMMON_ANODE=false`, HIGH=ON). Output latches are preloaded OFF before enabling output mode. Each pulse clears the other outputs first and switches OFF before its following dark interval. Tests have finite repetitions and no steady-ON mode.

The three resistors are reported to appear to be 220 ohms each. Check that each colour actually has its own correctly connected series resistor and that the circuit/driver is understood. Resistor appearance and low average duty do not verify peak current. Software cannot guarantee an OFF state during bootloader execution, an unexpected crash, or loss of power/control; its OFF handling applies during normal sketch execution.

## Compile without uploading

From the repository root:

```sh
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn arduino:avr:uno arduino/arduino_hardware_tests
```

This command only compiles. The file currently selects mode 1. All seven mode variants were compiled from temporary copies, leaving the main file unchanged.

## L1/L2 in the current plan

After hardware tests, use the unified recording-session sketch and send `RUN L1` or `RUN L2` in Serial Monitor at 115200 baud with newline endings. These run the audited ramp/PWM reconstruction, without an RGB start marker. Label their recordings **reconstructed original firmware**, not exact binary reproduction. The preserved original HEX remains evidence; restoring it is outside the current requested workflow. See [firmware instructions](../README.md) for the implementation details and limits.

## Offline verification results

Arduino CLI 1.6.0 / Arduino AVR core 1.8.6 / Uno target:

| Mode | Compile | Flash bytes | Global SRAM bytes | Simulated pulses |
|---:|---|---:|---:|---:|
| 0 | Passed | 2570 | 188 | 0 |
| 1 | Passed | 2674 | 188 | 5 |
| 2 | Passed | 2676 | 188 | 5 |
| 3 | Passed | 2676 | 188 | 5 |
| 4 | Passed | 2710 | 188 | 15 |
| 5 | Passed | 2760 | 188 | 1500 |
| 6 | Passed | 2708 | 188 | 300 |

For every mode, native simulated GPIO checks passed: outputs initialised OFF, correct pin/colour order, expected pulse count and requested delay widths/gaps, at most one active colour, and all outputs OFF after completion and subsequent loop calls. These checks do not measure real optical output, current or hardware timing. Original backups, analysis code and production hardware configuration were left unchanged.
