#pragma once
#include <string.h>
#include "generated_session.h"

// Flash tables stay in PROGMEM on the Uno. Host validation uses the same core.
template <typename T> T readTable(const T *address) {
  T value;
#ifdef __AVR__
  memcpy_P(&value, address, sizeof(T));
#else
  memcpy(&value, address, sizeof(T));
#endif
  return value;
}

template <typename Sink>
bool emitSchedule(uint8_t runIndex, int8_t selected, Sink &sink) {
  if (runIndex >= RUN_COUNT) return false;
  const RunSpec run = readTable(&RUNS[runIndex]);
  if (run.mode == LEGACY) return false;
  if ((run.mode == SELECTED || run.mode == IRREGULAR) && (selected < 0 || selected > 2)) return false;
  if (!sink.idle("pre_dark", PRE_DARK_US)) return false;
  if (run.mode == OFF) {
    if (!sink.idle("measurement_dark", DARK_CONTROL_US)) return false;
  } else {
    for (uint8_t i = 0; i < PREAMBLE_COUNT; ++i) {
      const Marker marker = readTable(&PREAMBLE[i]);
      if (!sink.pulse("preamble", i, marker.channel, marker.on_us, marker.off_us, false)) return false;
    }
    if (!sink.idle("settle_dark", SETTLE_DARK_US)) return false;
    if (run.mode == SINGLE) {
      for (uint16_t i = 0; i < SINGLE_PULSES; ++i)
        if (!sink.pulse("measurement", i, run.parameter, SINGLE_ON_US, SINGLE_OFF_US, false)) return false;
    } else if (run.mode == FIXED || run.mode == SELECTED) {
      const TimingProfile p = readTable(&PROFILES[run.mode == FIXED ? run.parameter : selected]);
      for (uint16_t i = 0; i < 3 * p.cycles; ++i)
        if (!sink.pulse("measurement", i, i % 3, p.on_us, p.off_us, false)) return false;
    } else if (run.mode == IRREGULAR) {
      const TimingProfile p = readTable(&PROFILES[selected]);
      const uint32_t baseGap = p.off_us > IRREGULAR_BASE_GAP_US ? p.off_us : IRREGULAR_BASE_GAP_US;
      for (uint16_t i = 0; i < IRREGULAR_SLOTS; ++i) {
        const uint8_t packed = pgm_read_byte(&IRREGULAR_DATA[run.parameter][i]);
        const uint32_t gap = baseGap * pgm_read_byte(&GAP_MULTIPLIERS[(packed >> 2) & 3]);
        if (!sink.pulse("measurement", i, packed & 3, p.on_us, gap, packed & 16)) return false;
      }
    }
  }
  return sink.idle("post_dark", POST_DARK_US);
}
