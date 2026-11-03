"""Tests for setup-facing Whisper model status and removal."""

from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from whisperx_studio import core, desktop_service as base
from whisperx_studio.managed_windows_service import WindowsService


class ManagedWindowsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core_patch = patch.object(core, "DATA", self.root)
        self.base_patch = patch.object(base, "DATA", self.root)
        self.core_patch.start()
        self.base_patch.start()
        self.service = WindowsService(emit=lambda *_: None)

    def tearDown(self):
        self.core_patch.stop()
        self.base_patch.stop()
        self.temp.cleanup()

    def test_state_exposes_whisper_model_installation_status(self):
        status = {
            "tiny": {"installed": True, "cached": True, "size_mb": 42.0},
            "base": {"installed": False, "cached": False, "size_mb": 0.0},
            "small": {"installed": False, "cached": True, "size_mb": 0.0},
            "medium": {"installed": False, "cached": False, "size_mb": 0.0},
            "large-v3": {"installed": False, "cached": False, "size_mb": 0.0},
        }
        with patch("whisperx_studio.managed_windows_service.model_statuses", return_value=status):
            state = self.service.state()
        self.assertEqual(state["whisper_models"], status)

    def test_remove_whisper_uses_allowlist_and_background_job(self):
        with patch.object(self.service, "start_job") as job:
            self.assertTrue(self.service.command("remove_asr", {"model": "tiny"}))
        self.assertEqual(job.call_args.args[0], "Whisper-Modell entfernen")
        work = job.call_args.args[1]
        with (
            patch("whisperx_studio.managed_windows_service.remove_model", return_value=True) as remove_model,
            patch.object(self.service, "push"),
        ):
            work(threading.Event())
        remove_model.assert_called_once_with("tiny")
        self.assertEqual(self.service.status, "Whisper tiny wurde lokal entfernt.")

        with self.assertRaises(ValueError):
            self.service.command("remove_asr", {"model": "tiny; shell"})


if __name__ == "__main__":
    unittest.main()
