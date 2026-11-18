#pragma once
#include <stdint.h>

// User-confirmed wiring: RED_PIN=9, GREEN_PIN=10, BLUE_PIN=11.
// COMMON_ANODE=false (common cathode): HIGH=on, LOW=off.
static const uint8_t LED_PINS[3] = {9, 10, 11}; // R, G, B
#ifndef RECORDING_LED_ACTIVE_HIGH
#define RECORDING_LED_ACTIVE_HIGH true
#endif
#ifndef RECORDING_HARDWARE_CONFIRMED
#define RECORDING_HARDWARE_CONFIRMED true
#endif
static const bool LED_ACTIVE_HIGH = RECORDING_LED_ACTIVE_HIGH;
static const bool HARDWARE_CONFIRMED = RECORDING_HARDWARE_CONFIRMED;
// Pin colours and polarity are confirmed. Set true after checking that the
// driver/current limits support the full-drive pulses, including the marker.
// No Trigger In wire is driven by this sketch.
