import csv
import importlib.util
import io
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("session", ROOT / "tools/prepare_recording_session.py")
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class RecordingSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = session.load_design()
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("native C++ compiler required for scheduler/firmware verification")
        cls.executables = {}
        for variant, flags in {"armed": ["-DRECORDING_HARDWARE_CONFIRMED=true"],
                               "unconfirmed": ["-DRECORDING_HARDWARE_CONFIRMED=false"],
                               "active_low": ["-DRECORDING_HARDWARE_CONFIRMED=true", "-DRECORDING_LED_ACTIVE_HIGH=false"]}.items():
            executable = cls.directory / variant
            subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror", *flags,
                            "-I" + str(ROOT / "tests/firmware_stubs"),
                            str(ROOT / "tests/recording_session_host.cpp"), "-o", str(executable)],
                           check=True, capture_output=True, text=True)
            cls.executables[variant] = executable

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def execute(self, command, variant="armed", simulation=None):
        args = [str(self.executables[variant]), "firmware", command + "\n"]
        if simulation:
            args.append(simulation)
        return subprocess.check_output(args, text=True)

    def test_scope_and_dependencies(self):
        runs = self.design["runs"]
        self.assertEqual(len(runs), 21)
        self.assertEqual(len({r["id"] for r in runs}), 21)
        self.assertEqual([r["id"] for r in runs[:2]], ["L1", "L2"])
        self.assertEqual([r["id"] for r in runs if r["mode"] == "off"], ["N1", "N2", "M1"])
        for run in runs:
            if run["experiment"] in ("C-A", "C-B", "D") or run["id"] in ("M2", "M3"):
                self.assertEqual(run["mode"], "selected")

    def test_generated_files_are_current(self):
        session.generate(check=True)

    def test_existing_digital_timelines_unchanged(self):
        expected = json.loads((ROOT / "tests/fixtures/recording_digital_schedule_hashes.json").read_text())
        actual = {run["id"] + "|" + choice:
                  hashlib.sha256(session.csv_text(session.rows_for_run(self.design, run, choice)).encode()).hexdigest()
                  for run in self.design["runs"] if run["mode"] != "legacy" for choice in ("T1", "T2", "T3")}
        self.assertEqual(actual, expected)

    def test_every_export_matches_shared_firmware_scheduler(self):
        for index, run in enumerate(self.design["runs"]):
            if run["mode"] == "legacy":
                self.assertEqual(session.rows_for_run(self.design, run, None), [])
                continue
            for choice in ("T1", "T2", "T3"):
                with self.subTest(run=run["id"], selected=choice):
                    expected = session.csv_text(session.rows_for_run(self.design, run, choice)).splitlines()[1:]
                    actual = subprocess.check_output([str(self.executables["armed"]), "schedule", str(index),
                                                      str(int(choice[1]) - 1)], text=True).splitlines()
                    self.assertEqual(actual, expected)

    def test_j_omissions_balance_variability_and_saved_identity(self):
        realised = []
        for sequence in range(2):
            slots = session.irregular_slots(self.design, sequence)
            self.assertEqual(len(slots), 300)
            self.assertEqual(sum(o for _, _, o in slots), 30)
            for c in range(3):
                self.assertEqual(sum(channel == c for channel, _, _ in slots), 100)
            self.assertEqual({g for _, g, _ in slots}, {0, 1, 2})
            for i in range(0, 300, 10):
                self.assertEqual(sum(o for _, _, o in slots[i:i + 10]), 1)
            realised.append(slots)
        self.assertNotEqual(*realised)

    def test_actual_commands_emit_expected_edges_and_end_off(self):
        for run in self.design["runs"]:
            if run["mode"] == "legacy":
                continue
            for choice in ("T1", "T2", "T3") if run["mode"] in ("selected", "irregular") else (None,):
                with self.subTest(run=run["id"], selected=choice):
                    command = "RUN " + run["id"] + (" " + choice if choice else "")
                    output = self.execute(command)
                    rows = session.rows_for_run(self.design, run, choice)
                    pulses = sum(row[2] != "-" and not row[3] for row in rows)
                    self.assertIn("DONE run=" + run["id"] + " ", output)
                    self.assertIn("emitted_edges=" + str(2 * pulses) + "\n", output)
                    self.assertIn("SIM rising=%d falling=%d active=0 outputs=3" % (pulses, pulses), output)

    def test_unconfirmed_never_drives_pins(self):
        output = self.execute("RUN T1", variant="unconfirmed")
        self.assertIn("ERROR confirm_hardware_config", output)
        self.assertIn("SIM rising=0 falling=0 active=0 outputs=0", output)

    def test_active_low_and_wraparound(self):
        for variant in ("armed", "active_low"):
            output = self.execute("RUN T1", variant=variant, simulation="wrap")
            self.assertIn("DONE run=T1 ", output)
            self.assertIn("SIM rising=2004 falling=2004 active=0 outputs=3", output)

    def test_late_run_aborts_off_without_replay(self):
        output = self.execute("RUN T1", simulation="late")
        self.assertIn("ABORTED run=T1 ", output)
        self.assertNotIn("DONE run=", output)
        self.assertIn("active=0 outputs=3", output)

    def test_bad_or_ambiguous_commands_have_no_flashes(self):
        for command in ("RUN L1 T1", "RUN unknown", "RUN CA1", "RUN CA1 T4", "RUN T1 T2",
                        "RUN M2 T2 extra", "INFO extra", "RUN " + "X" * 50):
            with self.subTest(command=command):
                output = self.execute(command)
                self.assertIn("ERROR ", output)
                self.assertIn("SIM rising=0 falling=0 active=0 outputs=3", output)
        self.assertIn("DONE run=T1", self.execute("RUN " + "X" * 50 + "\nRUN T1"))

    @staticmethod
    def report_fields(output, prefix):
        line = next(line for line in output.splitlines() if line.startswith(prefix))
        return dict(item.split("=", 1) for item in line.split() if "=" in item)

    def test_legacy_commands_run_without_marker_and_restore_timers(self):
        for run_id in ("L1", "L2"):
            for simulation in (None, "wrap"):
                with self.subTest(run=run_id, simulation=simulation):
                    output = self.execute("RUN " + run_id, simulation=simulation)
                    done = self.report_fields(output, "DONE ")
                    pwm = self.report_fields(output, "PWM ")
                    self.assertEqual(done["run"], run_id)
                    self.assertEqual(done["firmware_identity"], "reconstructed_original_firmware")
                    self.assertEqual(done["exact_binary_reproduction"], "0")
                    self.assertEqual(done["marker"], "none")
                    self.assertEqual(done["ramp_target_us"], "500")
                    self.assertEqual(done["zero_command_target_us"], "500")
                    self.assertEqual(done["nominal_pwm_period_us"], "2040")
                    self.assertGreaterEqual(int(done["measurement_elapsed_us"]), 5000000)
                    self.assertLess(int(done["measurement_elapsed_us"]), 5010000)
                    self.assertEqual(int(done["completed_stages"]), 3 * int(done["completed_rgb_cycles"]))
                    self.assertEqual(int(pwm["endpoints"]), int(done["completed_stages"]))
                    self.assertGreater(int(pwm["intermediate_calls"]), 0)
                    self.assertEqual(pwm["rgb_order"], "1")
                    # First ramp command follows one-second startup, never a marker pulse.
                    delta = (int(pwm["first_nonzero_us"]) - int(done["run_origin_us"])) & 0xFFFFFFFF
                    self.assertGreaterEqual(delta, 1000000)
                    self.assertLess(delta, 1000100)
                    self.assertIn("active=0 outputs=3", output)
                    self.assertIn("TIMERS restored=1", output)

    def test_legacy_single_stage_matches_audited_command_and_clock_trace(self):
        for channel in range(3):
            for wrap in (False, True):
                with self.subTest(channel=channel, wrap=wrap):
                    args = [str(self.executables["armed"]), "legacy-stage", str(channel)]
                    if wrap:
                        args.append("wrap")
                    output = subprocess.check_output(args, text=True)
                    trace = []
                    for row in csv.reader(io.StringIO(output)):
                        if row and row[0] == "TRACE":
                            trace.append((row[1], int(row[2]), int(row[3]), int(row[4])))
                    self.assertEqual([(e[2], e[3]) for e in trace[:3]], [(9, 0), (10, 0), (11, 0)])
                    self.assertEqual(trace[3][0], "M")
                    start = trace[3][1]
                    last_sample = None
                    ramp_values = []
                    for i, event in enumerate(trace[4:], start=4):
                        kind, timestamp, pin, value = event
                        if kind == "M":
                            last_sample = timestamp
                            continue
                        self.assertEqual(pin, 9 + channel)
                        elapsed = (last_sample - start) & 0xFFFFFFFF
                        if value == 255:
                            self.assertGreaterEqual(elapsed, 500)
                            endpoint = i
                            break
                        self.assertLess(elapsed, 500)
                        self.assertEqual(value, elapsed * 255 // 500)
                        ramp_values.append(value)
                    self.assertGreater(len(ramp_values), 1)
                    self.assertEqual(ramp_values, sorted(ramp_values))
                    # Endpoint immediately followed by ordered zero writes: no hold/ramp-down.
                    zeros = trace[endpoint + 1:endpoint + 4]
                    self.assertEqual([(e[0], e[2], e[3]) for e in zeros], [("A", 9, 0), ("A", 10, 0), ("A", 11, 0)])
                    dark = trace[endpoint + 4:]
                    self.assertTrue(all(e[0] == "M" for e in dark))
                    self.assertGreaterEqual((dark[-1][1] - dark[0][1]) & 0xFFFFFFFF, 500)
                    self.assertLess((dark[-1][1] - dark[0][1]) & 0xFFFFFFFF, 510)
                    self.assertIn("TIMERS restored=1", output)

    def test_legacy_guard_and_following_digital_runs(self):
        for variant, message in (("unconfirmed", "ERROR confirm_hardware_config"),
                                 ("active_low", "ERROR legacy_requires_D9_D10_D11_active_high")):
            output = self.execute("RUN L1", variant=variant)
            self.assertIn(message, output)
            self.assertIn("analog_calls=0", output)
        output = self.execute("RUN L1\nRUN T1\nRUN N1\nRUN L2\nRUN M2 T2")
        self.assertEqual([self.report_fields(line, "DONE ")["run"] for line in output.splitlines() if line.startswith("DONE ")],
                         ["L1", "T1", "N1", "L2", "M2"])
        self.assertIn("active=0 outputs=3", output)
        self.assertIn("TIMERS restored=1", output)

    def test_legacy_metadata_is_a_recipe_not_a_fabricated_edge_table(self):
        out = self.directory / "legacy_bundle"
        session.prepare(out, None)
        for run_id in ("L1", "L2"):
            meta = json.loads((out / (run_id + "_metadata.json")).read_text())
            recipe = json.loads((out / meta["command_schedule"]).read_text())
            self.assertEqual(meta["serial_command"], "RUN " + run_id)
            self.assertEqual(meta["firmware"]["identity"], "reconstructed_original_firmware")
            self.assertFalse(meta["exact_binary_reproduction"])
            self.assertFalse(recipe["exact_binary_reproduction"])
            self.assertFalse(recipe["start_marker"])
            self.assertEqual(recipe["ramp_us"], 500)
            self.assertEqual(recipe["zero_command_us"], 500)
            self.assertEqual(meta["planned_total_us"], 6000000)
            self.assertEqual(recipe["stage_pin_order"], [9, 10, 11])
            self.assertEqual(recipe["schedule_kind"], "elapsed_time_recipe_not_absolute_edge_timestamps")
            self.assertFalse((out / (run_id + "_schedule.csv")).exists())

    def test_serial_logger_accepts_legacy_recipe_and_preserves_identity(self):
        out = self.directory / "logger_bundle"
        session.prepare(out, None)
        capture_spec = importlib.util.spec_from_file_location("capture", ROOT / "tools/capture_arduino_run.py")
        capture = importlib.util.module_from_spec(capture_spec)
        capture_spec.loader.exec_module(capture)
        design_sha = session.design_hash(self.design)
        written = []

        class SimulatedPort:
            def __init__(self, *args, **kwargs):
                self.pending = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def write(self, value):
                written.append(value)
                if value == b"INFO\n":
                    self.pending.append(("INFO design_sha256=" + design_sha + " hardware_confirmed=1\n").encode())
                elif value == b"RUN L1\n":
                    self.pending.extend([b"START run=L1 firmware_identity=reconstructed_original_firmware\n",
                                         b"DONE run=L1 firmware_identity=reconstructed_original_firmware exact_binary_reproduction=0 completed_rgb_cycles=1000\n"])
                else:
                    raise AssertionError(value)

            def readline(self):
                return self.pending.pop(0) if self.pending else b""

        with mock.patch.dict("sys.modules", {"serial": types.SimpleNamespace(Serial=SimulatedPort)}), \
             mock.patch("sys.argv", ["capture", "--bundle", str(out), "--run", "L1", "--port", "simulated"]), \
             mock.patch("builtins.input", return_value=""), \
             mock.patch.object(capture.time, "sleep"), \
             mock.patch.object(capture.time, "monotonic", side_effect=iter(range(100))):
            capture.main()
        self.assertEqual(written, [b"INFO\n", b"RUN L1\n"])
        meta = json.loads((out / "L1_metadata.json").read_text())
        self.assertEqual(meta["status"], "controller_completed_camera_unchecked")
        self.assertEqual(meta["actual"]["controller_report_fields"]["firmware_identity"], "reconstructed_original_firmware")
        self.assertTrue((out / "L1_serial.jsonl").exists())

    def test_bundle_no_overwrite_and_unresolved_selection(self):
        out = self.directory / "unresolved"
        session.prepare(out, None)
        meta = json.loads((out / "CA1_metadata.json").read_text())
        self.assertIsNone(meta["command_schedule"])
        self.assertFalse((out / "CA1_schedule.csv").exists())
        self.assertEqual(len(list(csv.DictReader(io.StringIO((out / "run_sheet.csv").read_text())))), 21)
        with self.assertRaises(FileExistsError):
            session.prepare(out, "T1")
        resolved = self.directory / "selected"
        session.prepare(resolved, "T2")
        for run_id in ("CA1", "CA2", "CA3", "CB1", "CB2", "D", "M2", "M3"):
            meta = json.loads((resolved / (run_id + "_metadata.json")).read_text())
            self.assertEqual(meta["serial_command"], "RUN " + run_id + " T2")
            self.assertEqual((resolved / (run_id + "_schedule.csv")).read_text(),
                             (resolved / "CA1_schedule.csv").read_text())


if __name__ == "__main__":
    unittest.main()
