"""Validate and package an OFFLINE audit of the supplied Uno firmware backup.

No device/serial/programmer access. Function names and behavioural descriptions
in the evidence are manual interpretations of this binary's disassembly, not
recovered original symbols. This is not a general decompiler or AVR emulator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
EXPECTED_HEX_SHA256 = "5db94ba5ccb05123a765252579955536c032fdc4a0ddc6a79d7e06813b32f752"
PATTERN = re.compile(r"^\s*([0-9a-fA-F]+):\s*((?:[0-9a-fA-F]{2}\s+)+)\s*(\S.*)?$")


def read_ihex(path):
    memory, kinds = {}, {}
    base = 0
    ended = False
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line:
            continue
        if ended or not line.startswith(":"):
            raise ValueError(f"Invalid record/record after EOF at line {line_number}")
        record = bytes.fromhex(line[1:])
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) % 256:
            raise ValueError(f"Invalid Intel HEX size/checksum at line {line_number}")
        n, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        payload = record[4:4 + n]
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == 0:
            for offset, value in enumerate(payload):
                absolute = base + address + offset
                if absolute in memory:
                    raise ValueError("Overlapping Intel HEX data records")
                memory[absolute] = value
        elif kind == 1:
            if n or address:
                raise ValueError("Malformed EOF")
            ended = True
        elif kind in (2, 4):
            if n != 2 or address:
                raise ValueError("Malformed extended address")
            base = int.from_bytes(payload, "big") << (4 if kind == 2 else 16)
        elif kind in (3, 5):
            if n != 4:
                raise ValueError("Malformed start address record")
        else:
            raise ValueError(f"Unsupported HEX record type {kind}")
    if not ended or not memory:
        raise ValueError("Missing EOF or data")
    return memory, kinds


def verify_listing(path, memory):
    instructions = {}
    covered = set()
    lines = Path(path).read_text().splitlines()
    for line_number, line in enumerate(lines, 1):
        match = PATTERN.match(line)
        if not match:
            continue
        address = int(match[1], 16)
        payload = bytes.fromhex(match[2])
        for offset, value in enumerate(payload):
            if memory.get(address + offset) != value:
                raise ValueError(f"Listing byte mismatch at 0x{address + offset:x}, line {line_number}")
        if address in instructions:
            raise ValueError("Duplicate listing address")
        instructions[address] = dict(line=line_number, bytes=payload.hex(" "),
                                     instruction=match[3] or "", original=line)
        covered.update(range(address, address + len(payload)))
    if not instructions:
        raise ValueError("No disassembly bytes found")
    return instructions, covered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hex", type=Path, default=ROOT / "arduino_original_backup.hex")
    parser.add_argument("--disassembly", type=Path, default=ROOT / "arduino_original_disassembly.txt")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    hex_hash = hashlib.sha256(args.hex.read_bytes()).hexdigest()
    memory, kinds = read_ihex(args.hex)
    instructions, covered = verify_listing(args.disassembly, memory)
    if hex_hash != EXPECTED_HEX_SHA256:
        raise ValueError("This audit's annotated addresses apply only to the supplied known backup")
    if set(memory) != set(range(32768)):
        raise ValueError("Expected a complete 32 KiB flash image")
    # Instruction-byte anchors check that annotated constants/branches are present.
    anchors = {
        "ramp_limit_low_500": (0x62C, "24 ef"),
        "ramp_limit_high_500": (0x630, "21 e0"),
        "exit_ramp_at_elapsed_limit": (0x638, "f0 f4"),
        "scale_elapsed_divisor_low_500": (0x650, "24 ef"),
        "scale_elapsed_divisor_high_500": (0x652, "31 e0"),
        "next_update_increment_one_low_byte": (0x66A, "8f ef"),
        "repeat_ramp_clock_loop": (0x674, "d3 cf"),
        "terminal_level_255": (0x676, "2f ef"),
        "clear_immediately_after_terminal_write": (0x684, "0e 94 80 02"),
        "dark_limit_low_500": (0x69C, "64 3f"),
        "dark_limit_high_500": (0x69E, "71 40"),
        "repeat_dark_clock_loop": (0x6A4, "a8 f3"),
        "startup_delay_low": (0x92A, "60 34"),
        "startup_delay_middle": (0x92C, "72 44"),
        "startup_delay_high": (0x92E, "8f 40"),
        "stage_9_call": (0x944, "0e 94 f0 02"),
        "stage_10_call": (0x954, "0e 94 f0 02"),
        "stage_11_call": (0x964, "0e 94 f0 02"),
        "unconditional_in_practice_main_repeat_zero_test": (0x96E, "21 f3"),
    }
    evidence_anchors = {}
    for label, (address, expected) in anchors.items():
        entry = instructions[address]
        if entry["bytes"] != expected:
            raise ValueError(f"Unexpected instruction at {label}")
        evidence_anchors[label] = dict(address=f"0x{address:04x}", **entry)
    if [memory[0x68 + pin] for pin in [9, 10, 11]] != [3, 4, 7]:
        raise ValueError("Unexpected pin-to-timer table")
    args.output.mkdir(parents=True, exist_ok=False)
    for name, left, right in [("ramp_and_dark", 0x5E0, 0x6CC),
                              ("startup_and_main", 0x810, 0x97E),
                              ("scaled_channel_write", 0x500, 0x5E0),
                              ("analog_write", 0x1E4, 0x29C),
                              ("micros", 0x29C, 0x2E6)]:
        excerpt = [f"source line {entry['line']:5d}: {entry['original']}"
                   for address, entry in instructions.items() if left <= address < right]
        (args.output / f"{name}.txt").write_text("\n".join(excerpt) + "\n")
    result = dict(
        scope="offline artifact validation plus documented manual static analysis; no board I/O",
        hex_file=str(args.hex.resolve()), hex_sha256=hex_hash,
        disassembly_file=str(args.disassembly.resolve()),
        disassembly_sha256=hashlib.sha256(args.disassembly.read_bytes()).hexdigest(),
        audit_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        intel_hex_records={str(k): v for k, v in kinds.items()}, flash_bytes=len(memory),
        listed_bytes_checked=len(covered), unlisted_flash_byte_count=len(set(memory) - covered),
        listed_bytes_all_match=True,
        decoded_flash_sha256=hashlib.sha256(bytes(memory[i] for i in range(32768))).hexdigest(),
        manual_function_labels={"0x10e": "pinMode-output specialization", "0x14c": "digitalWrite",
            "0x1e4": "analogWrite", "0x29c": "micros", "0x500": "set all three channels to zero",
            "0x51e": "clamped single-pin analogWrite", "0x536": "write scaled nonzero channels",
            "0x5e0": "one elapsed-time ramp plus dark wait", "0x810": "initialisation and repeated stages"},
        findings=dict(ramp_timebase="micros elapsed-time threshold, not delay-per-duty-step",
            ramp_target_us=500, dark_wait_target_us=500, startup_wait_target_us=1_000_000,
            ramp_level_formula="floor(elapsed_us * 255 / 500) for elapsed_us < 500",
            update_schedule="next eligible update = previously sampled elapsed_us + 1; instruction costs and clock quantisation still apply",
            terminal_level=255, explicit_terminal_hold_us=0,
            pin_sequence=[9, 10, 11], physical_pin_colour_mapping_verified=False,
            nominal_RGB_budget_us_excluding_overhead=3000,
            timer_modes="8-bit phase-correct on Timer1/2 under standard reset-state assumptions",
            timer_prescaler=64, assumed_clock_hz=16_000_000,
            nominal_PWM_period_us=2040, nominal_PWM_hz=16_000_000 / (64 * 510),
            micros_quantum_us_for_standard_16MHz_clock=4,
            active_loop_command_parser_found=False),
        limitations=["Not an electrical/optical measurement or cycle-accurate execution simulation",
            "Actual oscillator/fuses/driver polarity/LED response not established by flash artifact",
            "Nominal waits exclude software overhead and possible ramp-loop overrun",
            "No historical DAT-to-firmware provenance", "No board communication or firmware changes"],
        instruction_anchors=evidence_anchors)
    (args.output / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ["flash_bytes", "listed_bytes_checked", "listed_bytes_all_match", "findings"]}, indent=2))


if __name__ == "__main__":
    main()
