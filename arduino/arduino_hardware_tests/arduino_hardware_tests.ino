// Change only TEST_MODE to select a test, then compile/upload this sketch.
// Uploading replaces the installed application: preserve/restore the original
// firmware as required for L1/L2 before using these hardware tests.
#define TEST_MODE 1

#include <Arduino.h>

#define RED_PIN 9
#define GREEN_PIN 10
#define BLUE_PIN 11
#define COMMON_ANODE false

// All tests run a finite number of times, then stay OFF until reset/power-up.
// Opening Serial Monitor may reset the Uno and automatically repeat the test.
const unsigned long STARTUP_DELAY_MS = 2000;
const unsigned long SLOW_ON_MS = 100;
const unsigned long SLOW_OFF_MS = 900;
const uint16_t SLOW_REPETITIONS = 5; // flashes per colour; RGB uses five cycles

const unsigned int FAST_ON_US = 1000;
const unsigned int FAST_OFF_US = 500;
const uint16_t FAST_RGB_CYCLES = 500;

const unsigned int LONG_ON_US = 5000;
const unsigned int LONG_OFF_US = 5000;
const uint16_t LONG_RGB_CYCLES = 100;

const uint8_t LED_ON = COMMON_ANODE ? LOW : HIGH;
const uint8_t LED_OFF = COMMON_ANODE ? HIGH : LOW;

#if TEST_MODE < 0 || TEST_MODE > 6
#error "TEST_MODE must be an integer from 0 to 6."
#endif

// AVR delayMicroseconds supports these short intervals directly. Keep editable
// microsecond durations within this range; use the millisecond helper for slow tests.
static_assert(FAST_ON_US > 0 && FAST_ON_US <= 16000, "FAST_ON_US must be 1..16000");
static_assert(FAST_OFF_US > 0 && FAST_OFF_US <= 16000, "FAST_OFF_US must be 1..16000");
static_assert(LONG_ON_US > 0 && LONG_ON_US <= 16000, "LONG_ON_US must be 1..16000");
static_assert(LONG_OFF_US > 0 && LONG_OFF_US <= 16000, "LONG_OFF_US must be 1..16000");

void allOff() {
  digitalWrite(RED_PIN, LED_OFF);
  digitalWrite(GREEN_PIN, LED_OFF);
  digitalWrite(BLUE_PIN, LED_OFF);
}

void flashSlow(uint8_t pin) {
  allOff();
  digitalWrite(pin, LED_ON);
  delay(SLOW_ON_MS);
  digitalWrite(pin, LED_OFF);
  allOff();
  delay(SLOW_OFF_MS);
}

void flashMicroseconds(uint8_t pin, unsigned int onUs, unsigned int offUs) {
  allOff();
  digitalWrite(pin, LED_ON);
  delayMicroseconds(onUs);
  digitalWrite(pin, LED_OFF);
  allOff();
  delayMicroseconds(offUs);
}

void testAllOff() {
  Serial.println(F("Mode 0: all LEDs OFF."));
  allOff();
}

void testRedOnly() {
  Serial.println(F("Mode 1: RED only, D9; slow visible flashes."));
  Serial.flush();
  for (uint16_t i = 0; i < SLOW_REPETITIONS; ++i) flashSlow(RED_PIN);
}

void testGreenOnly() {
  Serial.println(F("Mode 2: GREEN only, D10; slow visible flashes."));
  Serial.flush();
  for (uint16_t i = 0; i < SLOW_REPETITIONS; ++i) flashSlow(GREEN_PIN);
}

void testBlueOnly() {
  Serial.println(F("Mode 3: BLUE only, D11; slow visible flashes."));
  Serial.flush();
  for (uint16_t i = 0; i < SLOW_REPETITIONS; ++i) flashSlow(BLUE_PIN);
}

void testSequentialRgb() {
  Serial.println(F("Mode 4: slow RED -> GREEN -> BLUE, one colour at a time."));
  Serial.flush();
  for (uint16_t i = 0; i < SLOW_REPETITIONS; ++i) {
    flashSlow(RED_PIN);
    flashSlow(GREEN_PIN);
    flashSlow(BLUE_PIN);
  }
}

void testFastRgb() {
  Serial.println(F("Mode 5: RGB, 1 ms ON / 0.5 ms all-OFF (default timings)."));
  Serial.println(F("Fast pulses may look steady/mixed to your eyes."));
  Serial.flush();
  for (uint16_t i = 0; i < FAST_RGB_CYCLES; ++i) {
    flashMicroseconds(RED_PIN, FAST_ON_US, FAST_OFF_US);
    flashMicroseconds(GREEN_PIN, FAST_ON_US, FAST_OFF_US);
    flashMicroseconds(BLUE_PIN, FAST_ON_US, FAST_OFF_US);
  }
}

void testLongerRgb() {
  Serial.println(F("Mode 6: RGB, 5 ms ON / 5 ms all-OFF (default timings)."));
  Serial.flush();
  for (uint16_t i = 0; i < LONG_RGB_CYCLES; ++i) {
    flashMicroseconds(RED_PIN, LONG_ON_US, LONG_OFF_US);
    flashMicroseconds(GREEN_PIN, LONG_ON_US, LONG_OFF_US);
    flashMicroseconds(BLUE_PIN, LONG_ON_US, LONG_OFF_US);
  }
}

void setup() {
  // Preload the OFF output latches before switching pins from inputs to outputs.
  digitalWrite(RED_PIN, LED_OFF);
  digitalWrite(GREEN_PIN, LED_OFF);
  digitalWrite(BLUE_PIN, LED_OFF);
  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  allOff();

  Serial.begin(115200);
  Serial.println(F("RGB hardware test: R=D9, G=D10, B=D11; common cathode."));
  Serial.print(F("Selected TEST_MODE="));
  Serial.println(TEST_MODE);
  Serial.println(F("Starting automatically after the startup delay."));
  Serial.flush();
  delay(STARTUP_DELAY_MS);

  switch(TEST_MODE) {
    case 0: testAllOff(); break;
    case 1: testRedOnly(); break;
    case 2: testGreenOnly(); break;
    case 3: testBlueOnly(); break;
    case 4: testSequentialRgb(); break;
    case 5: testFastRgb(); break;
    case 6: testLongerRgb(); break;
    default: allOff(); break;
  }

  allOff();
  Serial.println(F("Test complete. All LEDs OFF. Reset to repeat."));
}

void loop() {
  allOff();
  delay(1000);
}
