#!/usr/bin/env python3
"""Log one prepared Arduino run; camera recording is started separately by the operator.

Requires pyserial. Never uploads firmware. Opening the Uno port may reset it.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--port", required=True, help="Exact known Uno serial port")
    args = parser.parse_args()
    if Path(args.run).name != args.run:
        parser.error("run must be a run ID")
    path = args.bundle / (args.run + "_metadata.json")
    metadata = json.loads(path.read_text())
    if metadata["status"] != "unrecorded":
        parser.error("run already attempted; preserve it and prepare a new bundle for a documented retake")
    if not metadata["command_schedule"] or not metadata["serial_command"]:
        parser.error("requires a resolved command schedule or legacy recipe; prepare with --selected for dependent runs")
    try:
        import serial
    except ImportError:
        parser.error("pyserial unavailable; install it in your chosen Python environment or use Serial Monitor")
    transcript = args.bundle / (args.run + "_serial.jsonl")
    with transcript.open("x") as log:
        def record(direction, value):
            log.write(json.dumps({"host_utc": datetime.now(timezone.utc).isoformat(),
                                  "direction": direction, "text": value}) + "\n")
            log.flush()
            print(value)

        with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=2) as board:
            # Allow the Uno's automatic USB reset/bootloader to finish, then ask
            # for identity even if the READY line has already been consumed.
            time.sleep(2)
            board.write(b"INFO\n")
            record("tx", "INFO")
            deadline = time.monotonic() + 5
            info = None
            while time.monotonic() < deadline:
                line = board.readline().decode("ascii", errors="replace").strip()
                if line:
                    record("rx", line)
                    if line.startswith("INFO "):
                        info = line
            if not info or ("design_sha256=" + metadata["design_sha256"]) not in info:
                raise SystemExit("Firmware design identity not verified; no RUN was sent")
            if "hardware_confirmed=1" not in info:
                raise SystemExit("Firmware hardware configuration is unconfirmed; no RUN was sent")
            metadata["actual"]["firmware_info"] = info
            print("Camera capture is separate. Check layout/movement condition:", metadata["layout"], metadata["motion"])
            input("Start a NEW camera recording, then press Enter to send " + metadata["serial_command"] + ": ")
            metadata["status"] = "attempt_started"
            metadata["actual"]["date_time_with_timezone"] = datetime.now(timezone.utc).isoformat()
            metadata["actual"]["serial_transcript_file"] = transcript.name
            path.write_text(json.dumps(metadata, indent=2) + "\n")
            command = metadata["serial_command"]
            record("tx", command)
            board.write((command + "\n").encode("ascii"))
            deadline = time.monotonic() + metadata["planned_total_us"] / 1e6 + 10
            while time.monotonic() < deadline:
                line = board.readline().decode("ascii", errors="replace").strip()
                if not line:
                    continue
                record("rx", line)
                if line.startswith(("DONE ", "ABORTED ", "ERROR ")):
                    fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
                    valid_done = line.startswith("DONE ") and fields.get("run") == args.run
                    metadata["status"] = "controller_completed_camera_unchecked" if valid_done else "controller_failed"
                    metadata["actual"]["done_report"] = line
                    metadata["actual"]["controller_report_fields"] = fields
                    path.write_text(json.dumps(metadata, indent=2) + "\n")
                    print("Stop and save the camera file; fill its path and quality checks in", path)
                    if not valid_done:
                        raise SystemExit(1)
                    return
            metadata["status"] = "controller_timeout_camera_unchecked"
            path.write_text(json.dumps(metadata, indent=2) + "\n")
            raise SystemExit("No completion report. Preserve the capture and transcript; do not silently rerun.")


if __name__ == "__main__":
    main()
