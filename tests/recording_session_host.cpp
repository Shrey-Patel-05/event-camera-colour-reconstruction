#include "firmware_stubs/Arduino.h"
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <vector>
#include "../arduino/recording_session/recording_session.ino"

FakeSerial Serial;
uint8_t TCCR1A = 1, TCCR1B = 3, TCCR2A = 1, TCCR2B = 4, OCR2A = 17;
uint16_t OCR1A = 19, OCR1B = 23;
static uint32_t simulatedTime = 0;
static uint64_t elapsedCalls = 0;
static bool injectLate = false;
static bool injected = false;
static uint8_t pinLevels[32] = {};
static bool pinOutputs[32] = {};
static uint32_t rising = 0, falling = 0;
static bool pwmActive[32] = {};
static uint32_t analogCalls = 0, intermediateCalls = 0;
static bool captureTrace = false;
struct Trace { char kind; uint32_t time; uint8_t pin; int value; };
static std::vector<Trace> trace;
static std::vector<uint8_t> endpointPins;
static uint32_t firstAnalogNonzero = 0;

uint32_t micros() {
  simulatedTime += 4;
  elapsedCalls += 4;
  if (injectLate && !injected && elapsedCalls > 2000000) {
    simulatedTime += 1000000; // interruption long enough to cross the next deadline
    injected = true;
  }
  if (captureTrace) trace.push_back({'M', simulatedTime, 0, 0});
  return simulatedTime;
}

static void checkOverlap() {
  uint8_t active = 0;
  for (uint8_t i = 0; i < 3; ++i)
    if (pinOutputs[LED_PINS[i]] && (pwmActive[LED_PINS[i]] || pinLevels[LED_PINS[i]] == onLevel())) ++active;
  if (active > 1) throw std::runtime_error("overlapping LED commands");
}

void pinMode(uint8_t pin, uint8_t) { pinOutputs[pin] = true; checkOverlap(); }
void digitalWrite(uint8_t pin, uint8_t value) {
  pwmActive[pin] = false;
  if (pin == 9) TCCR1A &= ~_BV(COM1A1);
  if (pin == 10) TCCR1A &= ~_BV(COM1B1);
  if (pin == 11) TCCR2A &= ~_BV(COM2A1);
  if (pinOutputs[pin] && pinLevels[pin] != value) {
    if (value == onLevel()) ++rising;
    else ++falling;
  }
  pinLevels[pin] = value;
  checkOverlap();
  simulatedTime += 4; // model a finite GPIO call
}

void analogWrite(uint8_t pin, int value) {
  if (value < 0 || value > 255) throw std::runtime_error("invalid analogWrite duty");
  ++analogCalls;
  if (captureTrace) trace.push_back({'A', simulatedTime, pin, value});
  pinMode(pin, OUTPUT);
  if (value && !firstAnalogNonzero) firstAnalogNonzero = simulatedTime;
  if (value == 255) endpointPins.push_back(pin);
  if (value == 0 || value == 255) {
    digitalWrite(pin, value == 255 ? HIGH : LOW);
  } else {
    // Check the actual configuration used when analogWrite requests carrier PWM.
    if ((TCCR1A & 3) != 1 || TCCR1B != 3 || (TCCR2A & 3) != 1 || TCCR2B != 4)
      throw std::runtime_error("legacy PWM mode/prescaler mismatch");
    ++intermediateCalls;
    pwmActive[pin] = true;
    if (pin == 9) { TCCR1A |= _BV(COM1A1); OCR1A = value; }
    if (pin == 10) { TCCR1A |= _BV(COM1B1); OCR1B = value; }
    if (pin == 11) { TCCR2A |= _BV(COM2A1); OCR2A = value; }
    checkOverlap();
    simulatedTime += 4;
  }
}

struct CsvSink {
  uint32_t cursor = 0;
  bool idle(const char *phase, uint32_t duration) {
    std::cout << phase << ",-1,-,0," << cursor << ',' << cursor + duration << ',' << cursor + duration << '\n';
    cursor += duration;
    return true;
  }
  bool pulse(const char *phase, uint16_t slot, uint8_t channel, uint32_t on, uint32_t gap, bool omitted) {
    std::cout << phase << ',' << slot << ',' << "RGB"[channel] << ',' << omitted << ','
              << cursor << ',' << cursor + on << ',' << cursor + on + gap << '\n';
    cursor += on + gap;
    return true;
  }
};

int main(int argc, char **argv) {
  if (argc < 3) return 2;
  if (std::string(argv[1]) == "schedule") {
    CsvSink sink;
    const int selected = argc > 3 ? atoi(argv[3]) : -1;
    if (!emitSchedule(atoi(argv[2]), selected, sink)) return 3;
    return 0;
  }
  if (argc > 3 && std::string(argv[3]) == "wrap") simulatedTime = 0xFFFFF000;
  if (argc > 3 && std::string(argv[3]) == "late") injectLate = true;
  setup();
  if (std::string(argv[1]) == "legacy-stage") {
    if (argc > 3 && std::string(argv[3]) == "wrap") simulatedTime = 0xFFFFFF00;
    // Deliberately begin with different modes to test setup AND restoration.
    TCCR1A = 2; TCCR1B = 11; TCCR2A = 2; TCCR2B = 7;
  }
  const uint8_t saved1a = TCCR1A, saved1b = TCCR1B, saved2a = TCCR2A, saved2b = TCCR2B, savedOcr2a = OCR2A;
  const uint16_t savedOcr1a = OCR1A, savedOcr1b = OCR1B;
  if (std::string(argv[1]) == "legacy-stage") {
    captureTrace = true;
    {
      LegacyPwmState pwm;
      const int channel = atoi(argv[2]);
      legacyStage(channel == 0 ? 255 : 0, channel == 1 ? 255 : 0, channel == 2 ? 255 : 0);
    }
    captureTrace = false;
    for (const auto &event : trace)
      std::cout << "TRACE," << event.kind << ',' << event.time << ',' << unsigned(event.pin) << ',' << event.value << '\n';
  } else {
  const std::string commands = argv[2];
  for (char c : commands) Serial.input.push_back(c);
  loop();
  }
  std::cout << Serial.output.str();
  uint8_t active = 0, outputs = 0;
  for (uint8_t i = 0; i < 3; ++i) {
    outputs += pinOutputs[LED_PINS[i]];
    active += pinOutputs[LED_PINS[i]] && (pwmActive[LED_PINS[i]] || pinLevels[LED_PINS[i]] == onLevel());
  }
  std::cout << "SIM rising=" << rising << " falling=" << falling << " active=" << unsigned(active)
            << " outputs=" << unsigned(outputs) << '\n';
  bool ordered = true;
  for (size_t i = 0; i < endpointPins.size(); ++i) if (endpointPins[i] != 9 + i % 3) ordered = false;
  std::cout << "PWM analog_calls=" << analogCalls << " intermediate_calls=" << intermediateCalls
            << " endpoints=" << endpointPins.size() << " rgb_order=" << ordered
            << " first_nonzero_us=" << firstAnalogNonzero << '\n';
  const bool restored = saved1a == TCCR1A && saved1b == TCCR1B && saved2a == TCCR2A && saved2b == TCCR2B &&
                        savedOcr1a == OCR1A && savedOcr1b == OCR1B && savedOcr2a == OCR2A;
  std::cout << "TIMERS restored=" << restored << '\n';
  return active ? 4 : 0;
}
