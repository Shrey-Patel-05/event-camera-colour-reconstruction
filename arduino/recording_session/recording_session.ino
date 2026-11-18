#include <Arduino.h>
#include <stdlib.h>
#include <string.h>
#include "hardware_config.h"
#include "schedule_core.h"

#if defined(__AVR__) && (!defined(__AVR_ATmega328P__) || F_CPU != 16000000UL)
#error "This audited PWM reconstruction targets the 16 MHz ATmega328P Uno."
#endif

// Digital modes are unchanged. Only reconstructed L uses analogWrite/PWM.
// No serial I/O, dynamic allocation or schedule export during illumination.
static char commandBuffer[40];
static uint8_t commandLength = 0;
static bool overflowed = false;

uint8_t offLevel() { return LED_ACTIVE_HIGH ? LOW : HIGH; }
uint8_t onLevel() { return LED_ACTIVE_HIGH ? HIGH : LOW; }

void allOff() {
  for (uint8_t i = 0; i < 3; ++i) digitalWrite(LED_PINS[i], offLevel());
}

// Audited ATmega328P timer setup: 8-bit phase-correct PWM at /64.
// Keep counters/prescalers running: their relative phase was not established.
// Restore controls/OCR values so a later digital RUN inherits its prior state.
struct LegacyPwmState {
  uint8_t t1a, t1b, t2a, t2b, ocr2a;
  uint16_t ocr1a, ocr1b;
  LegacyPwmState() : t1a(TCCR1A), t1b(TCCR1B), t2a(TCCR2A), t2b(TCCR2B),
                     ocr2a(OCR2A), ocr1a(OCR1A), ocr1b(OCR1B) {
    TCCR1A = _BV(WGM10);
    TCCR1B = _BV(CS11) | _BV(CS10);
    TCCR2A = _BV(WGM20);
    TCCR2B = _BV(CS22);
  }
  ~LegacyPwmState() {
    OCR1A = ocr1a; OCR1B = ocr1b; OCR2A = ocr2a;
    TCCR1A = t1a; TCCR1B = t1b; TCCR2A = t2a; TCCR2B = t2b;
  }
};

void legacyAllZero() {
  // 0x0500-0x051a: analogWrite zero, in D9 -> D10 -> D11 order.
  analogWrite(9, 0);
  analogWrite(10, 0);
  analogWrite(11, 0);
}

void __attribute__((noinline)) legacyWriteScaled(int red, int green, int blue, int brightness) {
  // 0x0536-0x05de: clamp brightness, skip zero tuple components, scale by /255.
  // No extra clearing of nonselected pins inside an individual ramp update.
  if (brightness > 255) brightness = 255;
  if (brightness < 0) brightness = 0;
  if (red) analogWrite(9, (int)((int32_t)red * brightness / 255));
  if (green) analogWrite(10, (int)((int32_t)green * brightness / 255));
  if (blue) analogWrite(11, (int)((int32_t)blue * brightness / 255));
}

void legacyStage(int red, int green, int blue) {
  // 0x05e0-0x06a4: elapsed-time ramp, endpoint then immediate clear, separate dark wait.
  legacyAllZero();
  const uint32_t start = micros();
  uint32_t nextUpdate = 0;
  while (true) {
    const uint32_t elapsed = (uint32_t)(micros() - start);
    if (elapsed >= LEGACY_RAMP_US) break;
    if (elapsed < nextUpdate) continue;
    const int brightness = (int)(elapsed * 255UL / LEGACY_RAMP_US);
    legacyWriteScaled(red, green, blue, brightness);
    nextUpdate = elapsed + LEGACY_UPDATE_INCREMENT_US;
  }
  legacyWriteScaled(red, green, blue, 255);
  legacyAllZero(); // no full-brightness hold, no ramp-down
  const uint32_t darkStart = micros();
  while ((uint32_t)(micros() - darkStart) < LEGACY_DARK_US) {}
}

void runReconstructedLegacy(const char *id) {
  allOff();
  Serial.print(F("START run=")); Serial.print(id);
  Serial.println(F(" selected=none firmware_identity=reconstructed_original_firmware exact_binary_reproduction=0 marker=none"));
  Serial.flush();
  const uint32_t origin = micros();
  uint32_t measurementStart, measurementElapsed, completedElapsed, cycles = 0;
  {
    LegacyPwmState pwm;
    legacyAllZero();
    // 0x0916-0x0932: audited one-second all-zero startup wait.
    const uint32_t startupStart = micros();
    while ((uint32_t)(micros() - startupStart) < LEGACY_STARTUP_US) {}
    measurementStart = micros();
    do {
      // 0x0938-0x096e: selected tuples and repetition order from the binary.
      legacyStage(255, 0, 0);
      legacyStage(0, 255, 0);
      legacyStage(0, 0, 255);
      legacyAllZero();
      ++cycles;
    } while ((uint32_t)(micros() - measurementStart) < LEGACY_MEASUREMENT_US);
    measurementElapsed = (uint32_t)(micros() - measurementStart);
    legacyAllZero();
  }
  allOff();
  completedElapsed = (uint32_t)(micros() - origin);
  Serial.print(F("DONE run=")); Serial.print(id);
  Serial.print(F(" firmware_identity=reconstructed_original_firmware exact_binary_reproduction=0 run_origin_us=")); Serial.print(origin);
  Serial.print(F(" measurement_start_us=")); Serial.print(measurementStart);
  Serial.print(F(" measurement_elapsed_us=")); Serial.print(measurementElapsed);
  Serial.print(F(" completed_elapsed_us=")); Serial.print(completedElapsed);
  Serial.print(F(" completed_rgb_cycles=")); Serial.print(cycles);
  Serial.print(F(" completed_stages=")); Serial.print(cycles * 3UL);
  Serial.print(F(" ramp_target_us=")); Serial.print(LEGACY_RAMP_US);
  Serial.print(F(" zero_command_target_us=")); Serial.print(LEGACY_DARK_US);
  Serial.println(F(" nominal_pwm_period_us=2040 marker=none"));
}

struct HardwareSink {
  uint32_t origin, cursor, maxLate, lateEdges, edgeCount;
  bool failed;
  HardwareSink() : origin(micros()), cursor(0), maxLate(0), lateEdges(0), edgeCount(0), failed(false) {}

  bool waitTarget(uint32_t target) {
    while ((int32_t)((uint32_t)(micros() - origin) - target) < 0) {}
    const uint32_t late = (uint32_t)(micros() - origin) - target;
    if (late > maxLate) maxLate = late;
    // Do not compress a pulse/gap to catch up after a substantial interruption.
    // Abort and mark the entire run incomplete if target is >100 us overdue.
    if (late > 100) { failed = true; allOff(); return false; }
    return true;
  }

  void edgeCompleted(uint32_t target) {
    const uint32_t late = (uint32_t)(micros() - origin) - target;
    if (late > maxLate) maxLate = late;
    if (late > 20) ++lateEdges;
    ++edgeCount;
  }

  bool idle(const char *, uint32_t duration) {
    allOff();
    cursor += duration;
    return waitTarget(cursor);
  }

  bool pulse(const char *, uint16_t, uint8_t channel, uint32_t on, uint32_t gap, bool omitted) {
    if (!waitTarget(cursor)) return false;
    if (!omitted) { digitalWrite(LED_PINS[channel], onLevel()); edgeCompleted(cursor); }
    if (!waitTarget(cursor + on)) return false;
    if (!omitted) { digitalWrite(LED_PINS[channel], offLevel()); edgeCompleted(cursor + on); }
    cursor += on + gap;
    return waitTarget(cursor);
  }
};

void printInfo() {
  Serial.print(F("INFO design_sha256=")); Serial.print(DESIGN_SHA);
  Serial.print(F(" hardware_confirmed=")); Serial.print(HARDWARE_CONFIRMED ? 1 : 0);
  Serial.print(F(" active_high=")); Serial.print(LED_ACTIVE_HIGH ? 1 : 0);
  Serial.print(F(" pins_RGB="));
  for (uint8_t i = 0; i < 3; ++i) { if (i) Serial.print(','); Serial.print(LED_PINS[i]); }
  Serial.println(F(" trigger_output=none"));
}

void handleCommand(char *line) {
  char *op = strtok(line, " \t");
  if (!op) return;
  if (!strcmp(op, "INFO") && !strtok(NULL, " \t")) { printInfo(); return; }
  if (strcmp(op, "RUN")) { Serial.println(F("ERROR expected INFO or RUN <id> [T1|T2|T3]")); return; }
  char *id = strtok(NULL, " \t");
  char *choice = strtok(NULL, " \t");
  if (!id || strtok(NULL, " \t")) { Serial.println(F("ERROR argument_count")); return; }
  int8_t selected = -1;
  if (choice) {
    if (strlen(choice) != 2 || choice[0] != 'T' || choice[1] < '1' || choice[1] > '3') {
      Serial.println(F("ERROR selection_must_be_T1_T2_T3")); return;
    }
    selected = choice[1] - '1';
  }
  int8_t found = -1;
  RunSpec run;
  for (uint8_t i = 0; i < RUN_COUNT; ++i) {
    run = readTable(&RUNS[i]);
    if (!strcmp(id, run.id)) { found = i; break; }
  }
  if (found < 0) { Serial.println(F("ERROR unknown_run_id")); return; }
  const bool needsSelection = run.mode == SELECTED || run.mode == IRREGULAR;
  if (needsSelection != (selected >= 0)) {
    Serial.println(F("ERROR selected_runs_require_T_choice_others_forbid_it")); return;
  }
  if (!HARDWARE_CONFIRMED) { Serial.println(F("ERROR confirm_hardware_config_before_build")); return; }
  if (run.mode == LEGACY) {
    if (!LED_ACTIVE_HIGH || LED_PINS[0] != 9 || LED_PINS[1] != 10 || LED_PINS[2] != 11) {
      Serial.println(F("ERROR legacy_requires_D9_D10_D11_active_high")); return;
    }
    runReconstructedLegacy(run.id);
    return;
  }
  allOff();
  Serial.print(F("START run=")); Serial.print(run.id);
  Serial.print(F(" selected=")); Serial.println(choice ? choice : "none");
  Serial.flush();
  HardwareSink sink;
  const bool ok = emitSchedule(found, selected, sink);
  allOff();
  const uint32_t completedElapsed = (uint32_t)(micros() - sink.origin);
  Serial.print(ok ? F("DONE run=") : F("ABORTED run=")); Serial.print(run.id);
  Serial.print(F(" run_origin_us=")); Serial.print(sink.origin);
  Serial.print(F(" planned_end_us=")); Serial.print(sink.cursor);
  Serial.print(F(" completed_elapsed_us=")); Serial.print(completedElapsed);
  Serial.print(F(" max_observed_lateness_us=")); Serial.print(sink.maxLate);
  Serial.print(F(" edges_over_20us=")); Serial.print(sink.lateEdges);
  Serial.print(F(" emitted_edges=")); Serial.println(sink.edgeCount);
}

void setup() {
  // With unverified hardware, leave the LED pins as inputs. No light is commanded.
  if (HARDWARE_CONFIRMED) {
    for (uint8_t i = 0; i < 3; ++i) {
      digitalWrite(LED_PINS[i], offLevel()); // preload inactive level before OUTPUT
      pinMode(LED_PINS[i], OUTPUT);
    }
    allOff();
  }
  Serial.begin(115200);
  Serial.println(F("READY recording_session_v1; newline commands; no automatic replay"));
  printInfo();
}

void loop() {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflowed) Serial.println(F("ERROR command_too_long"));
      else { commandBuffer[commandLength] = '\0'; handleCommand(commandBuffer); }
      commandLength = 0;
      overflowed = false;
    } else if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = c;
    } else overflowed = true;
  }
}
