#pragma once
#include <stdint.h>
#include <deque>
#include <sstream>
#include <string>
#define F(x) x
#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define _BV(bit) (1U << (bit))
#define WGM10 0
#define WGM20 0
#define CS10 0
#define CS11 1
#define CS22 2
#define COM1A1 7
#define COM1B1 5
#define COM2A1 7

extern uint8_t TCCR1A, TCCR1B, TCCR2A, TCCR2B, OCR2A;
extern uint16_t OCR1A, OCR1B;

uint32_t micros();
void digitalWrite(uint8_t pin, uint8_t value);
void analogWrite(uint8_t pin, int value);
void pinMode(uint8_t pin, uint8_t mode);

struct FakeSerial {
  std::ostringstream output;
  std::deque<char> input;
  void begin(unsigned long) {}
  void flush() {}
  int available() { return input.size(); }
  char read() { char c = input.front(); input.pop_front(); return c; }
  template <typename T> void print(T value) { output << value; }
  void print(uint8_t value) { output << unsigned(value); }
  template <typename T> void println(T value) { print(value); output << '\n'; }
};
extern FakeSerial Serial;
