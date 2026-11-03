"""Actual local adapter tests; no Windows/GPU execution is implied."""

import copy
import json
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

from whisperx_studio import core, desktop_service as base
from whisperx_studio.windows_service import WindowsService, serve


class WindowsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core_patch = patch.object(core, "DATA", self.root)
        self.base_patch = patch.object(base, "DATA", self.root)
        self.core_patch.start()
        self.base_patch.start()
        self.events = []
        self.service = WindowsService(
            emit=lambda kind, data: self.events.append((kind, data))
        )
        self.source = self.root / "recordings/Windows Aufnahme ü.wav"
        self.source.parent.mkdir()
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 16000)

    def tearDown(self):
        self.core_patch.stop()
        self.base_patch.stop()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 5
        while self.service.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.service.busy)

    def test_windows_recording_import_and_finalization_use_host_wav(self):
        original = self.source.read_bytes()
        self.service.command("external_record_start", {"path": str(self.source)})
        self.assertTrue(self.service.state()["recording"])
        self.assertEqual(self.service.state()["platform"], "windows-container")
        with self.assertRaises(ValueError):
            self.service.command("metadata", {"title": "locked"})
        self.service.command("record_stop", {})
        self.wait()
        self.assertTrue(self.service.project)
        self.assertEqual(self.service.doc.duration, 1)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.service.state()["recording"])

    def test_portable_data_recording_path_maps_to_windows_workspace(self):
        self.service.command(
            "external_record_start",
            {"path": "/data/recordings/Windows Aufnahme ü.wav"},
        )
        self.assertEqual(self.service.record_path, self.source.resolve())
        self.service.command("shutdown", {})

    def test_portable_data_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            self.service.command(
                "external_record_start", {"path": "/data/recordings/../secret.wav"}
            )

    def test_native_platform_marker_is_reported_from_environment(self):
        with patch.dict(os.environ, {"WINWHISPER_PLATFORM": "windows-native"}):
            self.assertEqual(self.service.state()["platform"], "windows-native")

    def test_external_recording_refuses_paths_outside_recordings(self):
        outside = self.root / "elsewhere.wav"
        outside.write_bytes(self.source.read_bytes())
        with self.assertRaises(ValueError):
            self.service.command("external_record_start", {"path": str(outside)})
        self.assertFalse(self.service.state()["recording"])

    def test_recording_start_never_invokes_linux_audio_recorder(self):
        with patch.object(base.subprocess, "Popen") as popen:
            self.service.command("external_record_start", {"path": str(self.source)})
        popen.assert_not_called()
        self.service.command("shutdown", {})

    def test_browser_microphone_ids_are_accepted_and_settings_validated(self):
        self.service.command(
            "settings", {"microphone": "browser-device-id", "diarize": True}
        )
        self.assertEqual(self.service.settings["microphone"], "browser-device-id")
        self.assertTrue(
            json.loads((self.root / "settings.json").read_text())["diarize"]
        )
        before = copy.deepcopy(self.service.settings)
        for values in [
            {"diarize": "yes"},
            {"device": "bad"},
            {"microphone": {}},
            {"microphone": "x" * 513},
        ]:
            with self.assertRaises(ValueError):
                self.service.command("settings", values)
            self.assertEqual(self.service.settings, before)

    def test_only_two_explicit_local_models_can_be_downloaded(self):
        with (
            patch.object(self.service, "start_job") as job,
            patch("whisperx_studio.windows_service.find_ollama", return_value="ollama"),
        ):
            for model in ["remote:cloud", "gemma4:e2b; shell", "arbitrary-model"]:
                with self.assertRaises(ValueError):
                    self.service.command("model_pull", {"model": model})
            job.assert_not_called()
            self.service.command("model_pull", {"model": "gemma4:e2b"})
            self.assertEqual(job.call_count, 1)

    def test_model_download_requires_optional_ollama(self):
        with patch("whisperx_studio.windows_service.find_ollama", return_value=None):
            with self.assertRaisesRegex(ValueError, "Ollama ist nicht installiert"):
                self.service.command("model_pull", {"model": "gemma4:e2b"})

    def test_malformed_desktop_requests_do_not_crash_private_service(self):
        stream = io.StringIO(
            '[]\nnull\n{"id":3,"action":"logs"}\n{"id":4,"action":"shutdown"}\n'
        )
        with patch("sys.stdin", stream):
            serve(self.service)
        results = [data for kind, data in self.events if kind == "result"]
        self.assertIn("error", results[0])
        self.assertEqual(results[2]["id"], 3)
        self.assertTrue(results[-1]["value"])
        self.assertTrue(self.service.closed)

    def test_file_commands_reject_host_filesystem_paths(self):
        for action in ["load_audio", "open_project", "import_transcript"]:
            with self.assertRaises(ValueError):
                self.service.command(action, {"path": "/etc/passwd"})

    def test_imported_project_cannot_redirect_workspace_writes(self):
        project = core.new_project(
            self.source, 1, self.source, self.root / "projects/safe"
        )
        project["directory"] = "/app"
        file = self.root / "malicious.json"
        core.atomic_json(file, project)
        self.service.command("open_project", {"path": str(file)})
        self.wait()
        self.assertIsNone(self.service.project)
        self.assertTrue(self.service.status.startswith("Fehler:"))

    def test_ollama_failure_does_not_block_transcription(self):
        calls = []

        class Client:
            def request(self, endpoint):
                self_test.assertEqual(endpoint, "/api/ps")
                raise RuntimeError("not running")

        self_test = self
        with (
            patch("whisperx_studio.windows_service.OllamaClient", Client),
            patch.object(self.service, "require_project", side_effect=lambda: calls.append("project")),
            patch.object(self.service, "push"),
            patch.object(self.service, "run_process", side_effect=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stop-after-ollama-check"))),
        ):
            self.service.project = {
                "directory": str(self.root / "projects/p"),
                "segments": [],
            }
            class Doc:
                def render(self, target, cancel=None):
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                    Path(target).write_bytes(b"")
                    return Path(target)
            self.service.doc = Doc()
            with self.assertRaisesRegex(RuntimeError, "stop-after-ollama-check"):
                self.service.transcribe_work(threading.Event())
        self.assertEqual(calls, ["project"])
        self.assertTrue(any("Ollama ist nicht aktiv" in text for text in self.service.logs))


if __name__ == "__main__":
    unittest.main()
