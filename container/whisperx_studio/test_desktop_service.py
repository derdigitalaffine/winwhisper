import copy
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

import numpy as np

from .core import (
    atomic_json,
    decode_audio,
    fingerprint,
    new_project,
    read_peaks,
    transcript_segments,
)
from .desktop_service import DesktopService


class DesktopServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_patch = patch(
            "whisperx_studio.desktop_service.DATA", self.root / "data"
        )
        self.data_patch.start()
        self.events = []
        self.service = DesktopService(
            emit=lambda kind, data: self.events.append((kind, data))
        )
        self.source = self.root / "original.wav"
        with wave.open(str(self.source), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes(np.full(32000, 1000, dtype="<i2").tobytes())
        self.preview = self.root / "preview.wav"
        duration = decode_audio(self.source, self.preview)
        p = new_project(self.source, duration, self.preview, self.root / "project")
        p["segments"] = transcript_segments(
            {
                "segments": [
                    {
                        "start": 0,
                        "end": 1,
                        "speaker": "SPEAKER_00",
                        "text": "Ich übernehme die Prüfung bis Freitag.",
                    }
                ]
            }
        )
        p["speakers"] = {"SPEAKER_00": "Anna"}
        self.service.activate(p, read_peaks(self.preview))

    def tearDown(self):
        self.data_patch.stop()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 5
        while self.service.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.service.busy, "Hintergrundauftrag blieb hängen")

    def test_state_exports_seven_selectable_profiles_and_existing_transcript(self):
        state = self.service.state()
        self.assertEqual(len(state["profiles"]), 7)
        self.assertEqual(
            state["segments"][0]["text"], "Ich übernehme die Prüfung bis Freitag."
        )
        self.assertEqual(state["audio_url"], self.preview.as_uri())
        self.assertEqual(state["reports"], [])

    def test_cut_undo_roundtrip_and_original_stays_unchanged(self):
        original = self.source.read_bytes()
        self.service.command("cut", {"start": 0.5, "end": 1})
        self.assertEqual(self.service.doc.duration, 1.5)
        self.assertEqual(self.service.project["segments"], [])
        self.assertTrue(self.service.state()["can_undo"])
        self.service.command("undo", {})
        self.assertEqual(self.service.doc.duration, 2)
        self.assertEqual(len(self.service.project["segments"]), 1)
        self.assertEqual(self.source.read_bytes(), original)

    def test_text_and_speaker_changes_persist(self):
        self.service.command(
            "speakers", {"names": {"SPEAKER_00": "Anna", "SPEAKER_01": "Ben"}}
        )
        self.service.command(
            "update_segment",
            {"id": "s00001", "text": "Korrigierter Wortlaut.", "speaker": "SPEAKER_01"},
        )
        saved = json.loads(self.service.project_path.read_text())
        self.assertEqual(saved["segments"][0]["speaker"], "SPEAKER_01")
        self.assertEqual(saved["segments"][0]["text"], "Korrigierter Wortlaut.")
        self.assertIn("original_text", saved["segments"][0])

    def test_failed_save_restores_text_cut_and_project_destination(self):
        before = copy.deepcopy(self.service.project)
        saved = self.service.project_path.read_bytes()
        destination = self.service.project_path
        with patch(
            "whisperx_studio.desktop_service.atomic_json",
            side_effect=OSError("Kein Speicherplatz"),
        ):
            for action, data in [
                ("update_segment", {"id": "s00001", "text": "Nicht gespeichert"}),
                ("cut", {"start": 0.2, "end": 0.5}),
                ("save_as", {"path": str(self.root / "new.json")}),
            ]:
                with self.assertRaises(OSError):
                    self.service.command(action, data)
                self.assertEqual(self.service.project, before)
                self.assertEqual(self.service.project_path, destination)
                self.assertEqual(self.service.doc.duration, 2)
                self.assertEqual(destination.read_bytes(), saved)

    def test_activation_failure_keeps_previous_project(self):
        previous = self.service.project
        with patch(
            "whisperx_studio.desktop_service.atomic_json",
            side_effect=OSError("Schreibfehler"),
        ):
            with self.assertRaises(OSError):
                self.service.activate(
                    new_project(self.source, 2, self.preview, self.root / "other"),
                    read_peaks(self.preview),
                )
        self.assertIs(self.service.project, previous)

    def test_interrupted_atomic_replace_keeps_saved_file_and_removes_temporary(self):
        path = self.service.project_path
        before = path.read_bytes()
        with patch(
            "whisperx_studio.core.os.replace",
            side_effect=OSError("Umbenennen fehlgeschlagen"),
        ):
            with self.assertRaises(OSError):
                self.service.command("metadata", {"title": "Nicht gespeichert"})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(path.parent.glob("*.tmp")))
        self.assertEqual(self.service.project["title"], json.loads(before)["title"])

    def test_state_omits_word_alignment_but_project_preserves_it(self):
        words = [{"word": "Beispiel", "start": 0, "end": 1, "score": 0.99}] * 5000
        self.service.project["segments"][0]["words"] = words
        self.service.project["reports"] = [
            {"markdown": "# Text", "items": [{"unused": words}], "tasks": words}
        ]
        state = self.service.state()
        self.assertNotIn("words", state["segments"][0])
        self.assertNotIn("items", state["reports"][0])
        self.assertNotIn("tasks", state["reports"][0])
        self.assertEqual(state["reports"][0]["created"], "")
        self.assertLess(len(json.dumps(state)), 15000)
        self.assertEqual(self.service.project["segments"][0]["words"], words)

    def test_callback_failure_reaps_real_subprocess_before_unlock(self):
        seen = []

        def fail(line):
            seen.append(self.service.proc)
            raise ValueError("Ungültige Ausgabe")

        with self.assertRaisesRegex(ValueError, "Ungültige Ausgabe"):
            self.service.run_process(
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "import time; print('ready'); time.sleep(30)",
                ],
                threading.Event(),
                fail,
            )
        self.assertIsNotNone(seen[0].poll())
        self.assertIsNone(self.service.proc)

    def test_quiet_process_cancels_and_next_job_starts(self):
        self.service.start_job(
            "Test",
            lambda cancel: self.service.run_process(
                [sys.executable, "-c", "import time; time.sleep(30)"], cancel
            ),
        )
        deadline = time.monotonic() + 3
        while self.service.proc is None and time.monotonic() < deadline:
            time.sleep(0.01)
        proc = self.service.proc
        self.assertIsNotNone(proc)
        self.service.command("cancel", {})
        self.wait()
        self.assertIsNotNone(proc.poll())
        completed = threading.Event()
        self.service.start_job("Nächster Auftrag", lambda cancel: completed.set())
        self.wait()
        self.assertTrue(completed.is_set())

    def test_cancel_before_start_creates_no_process(self):
        cancel = threading.Event()
        cancel.set()
        with patch("whisperx_studio.desktop_service.subprocess.Popen") as popen:
            with self.assertRaises(InterruptedError):
                self.service.run_process(["unused"], cancel)
        popen.assert_not_called()

    def test_process_ignoring_terminate_is_forcibly_reaped(self):
        cancel = threading.Event()
        seen = []

        def ready(line):
            seen.append(self.service.proc)
            cancel.set()

        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready',flush=True); time.sleep(30)"
        with self.assertRaises(InterruptedError):
            self.service.run_process([sys.executable, "-u", "-c", code], cancel, ready)
        self.assertEqual(seen[0].returncode, -signal.SIGKILL)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux parent-death signal")
    def test_worker_stops_even_when_its_service_crashes(self):
        marker = self.root / "guard-signal.txt"
        pidfile = self.root / "guard-pid.txt"
        child_code = "import signal,time,pathlib,sys; p=pathlib.Path(sys.argv[1]); signal.signal(signal.SIGTERM,lambda *_:(p.write_text('terminated'),sys.exit(0))); print('ready',flush=True); time.sleep(30)"
        parent_code = "import os,sys,subprocess,pathlib; from whisperx_studio.desktop_service import guarded_command; p=subprocess.Popen(guarded_command([sys.executable,'-u','-c',sys.argv[1],sys.argv[2]]),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True); assert p.stdout.readline().strip()=='ready'; pathlib.Path(sys.argv[3]).write_text(str(p.pid)); os._exit(0)"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    parent_code,
                    child_code,
                    str(marker),
                    str(pidfile),
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(
                marker.exists(), "Kindprozess hat den Dienstabsturz nicht erkannt"
            )
            self.assertEqual(marker.read_text(), "terminated")
        finally:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_corrupt_preview_is_rebuilt_from_unchanged_original(self):
        original = self.source.read_bytes()
        self.preview.write_bytes(b"broken")
        self.service.command("open_project", {"path": str(self.service.project_path)})
        self.wait()
        with wave.open(str(self.preview)) as audio:
            self.assertEqual(audio.getnframes(), 32000)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(len(self.service.project["segments"]), 1)

    def test_bad_project_never_replaces_current_project(self):
        before = copy.deepcopy(self.service.project)
        for value in [
            [],
            {"format": "whisperx-studio", "version": 1},
            {**before, "reports": [None]},
            {**before, "segments": [None]},
            {**before, "duration": float("inf")},
        ]:
            path = self.root / "bad.json"
            path.write_text(json.dumps(value))
            self.service.command("open_project", {"path": str(path)})
            self.wait()
            self.assertEqual(self.service.project, before)
            self.assertTrue(self.service.status.startswith("Fehler:"))

    def test_corrupt_recent_and_settings_do_not_prevent_startup(self):
        for recent, settings in [
            ({}, []),
            (
                [str(self.root / "invalid.json")],
                {"device": "invalid", "diarize": "yes", "live": False},
            ),
        ]:
            atomic_json(self.root / "data/recent.json", recent)
            atomic_json(self.root / "data/settings.json", settings)
            atomic_json(self.root / "invalid.json", [])
            service = DesktopService(emit=lambda *_: None)
            self.assertEqual(service.recent, [])
            self.assertEqual(service.settings["device"], "auto")
            self.assertFalse(service.settings["diarize"])

    def test_malformed_ipc_does_not_crash_real_service(self):
        result = subprocess.run(
            [sys.executable, "-m", "whisperx_studio.desktop_service"],
            input='[]\nnull\n{"id":3,"action":"logs"}\n{"id":4,"action":"shutdown"}\n',
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(responses[0]["data"]["error"])
        self.assertEqual(responses[2]["data"]["id"], 3)
        self.assertTrue(responses[-1]["data"]["value"])

    def test_audio_undo_keeps_reports_created_after_the_cut(self):
        self.service.command("cut", {"start": 0.5, "end": 1})
        self.service.project["reports"] = [
            {
                "kind": "tasks",
                "model": "gemma4:e2b",
                "markdown": "# Nach dem Schnitt erstellt",
            }
        ]
        self.service.command("metadata", {"title": "Neuer Sitzungstitel"})
        self.service.command("undo", {})
        self.assertEqual(self.service.project["title"], "Neuer Sitzungstitel")
        self.assertEqual(
            self.service.project["reports"][0]["markdown"],
            "# Nach dem Schnitt erstellt",
        )

    def test_legacy_reports_are_preserved_and_labeled(self):
        old = {
            "model": "gemma4:e2b",
            "markdown": "# Altes Ergebnis",
            "fingerprint": fingerprint(self.service.project),
            "sources": [],
            "created": "2026-11-03",
        }
        self.service.project["reports"] = [copy.deepcopy(old)]
        state = self.service.state()
        self.assertEqual(state["reports"][0]["kind"], "legacy")
        self.assertEqual(self.service.project["reports"][0], old)

    def test_locked_edits_fail_but_waveform_remains_available(self):
        self.service.busy = True
        with self.assertRaises(ValueError):
            self.service.command("cut", {"start": 0.2, "end": 0.4})
        peaks = self.service.command(
            "waveform", {"start": 0, "end": 2, "width": 100000}
        )
        self.assertEqual(len(peaks), 2200)
        self.service.busy = False

    def test_original_cannot_be_used_as_export_destination(self):
        with self.assertRaises(ValueError):
            self.service.destination(self.source)
        with self.assertRaises(ValueError):
            self.service.destination(self.service.project_path)

    def test_only_requested_kind_is_sent_to_worker_and_added(self):
        self.service.models = ["gemma4:e2b"]
        captured = {}

        def process(command, cancel, on_line=None, secret=None):
            request_path = Path(command[3])
            p = json.loads(request_path.read_text())
            captured.update(p["requested_report"])
            r = {
                "kind": "tasks",
                "label": "Aufgabenliste",
                "model": "gemma4:e2b",
                "markdown": "# Aufgaben",
                "fingerprint": fingerprint(p),
                "sources": p["segments"],
                "created": "2026-11-03",
                "chunks": 1,
                "warnings": [],
                "tasks": [],
            }
            result = request_path.parent / "report-0.json"
            atomic_json(result, r)
            on_line(json.dumps({"type": "report", "data": str(result)}))

        with patch.object(self.service, "run_process", side_effect=process):
            self.service.generate_work(
                {
                    "kind": "tasks",
                    "models": ["gemma4:e2b"],
                    "options": {"verify": False},
                },
                self.service.cancel_event,
            )
        self.assertEqual(captured["kind"], "tasks")
        self.assertEqual(len(self.service.project["reports"]), 1)
        self.assertEqual(self.service.project["reports"][0]["kind"], "tasks")
        self.assertTrue(any(k == "report_ready" for k, v in self.events))

    def test_saved_project_can_be_opened_again_in_background(self):
        self.service.command("open_project", {"path": str(self.service.project_path)})
        self.wait()
        self.assertEqual(self.service.project["title"], "original")
        self.assertEqual(len(self.service.project["segments"]), 1)

    def test_record_stop_finalizes_audio_before_import(self):
        class Recorder:
            stopped = False

            def poll(self):
                return 0 if self.stopped else None

            def send_signal(self, value):
                self.stopped = value == signal.SIGINT

            def wait(self, timeout=None):
                return 0

        recorder = Recorder()
        self.service.record_proc = recorder
        self.service.record_path = self.source
        self.service.stop_recording()
        self.wait()
        self.assertTrue(recorder.stopped)
        self.assertEqual(self.service.doc.duration, 2)
        self.assertIsNone(self.service.record_proc)

    def test_record_stop_waits_for_last_buffered_live_segment(self):
        class Done:
            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        self.service.record_proc = Done()
        self.service.record_path = self.source
        self.service.live_proc = Done()
        self.service.live_stop = self.root / "stop.signal"

        def late_reader():
            time.sleep(0.1)
            self.service.live_segments.append(
                {"start": 0, "end": 1, "text": "Letzter Satz."}
            )

        reader = threading.Thread(target=late_reader)
        self.service.live_reader_thread = reader
        reader.start()
        self.service.stop_recording()
        self.wait()
        self.assertEqual(self.service.project["segments"][0]["text"], "Letzter Satz.")
        self.assertTrue(self.service.project["preliminary"])

    def test_wave_reader_after_immediate_stop_returns_cleanly(self):
        self.service.record_proc = None
        self.service.record_wave()


if __name__ == "__main__":
    unittest.main()
