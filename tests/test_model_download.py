"""Unit tests for the verbose Whisper model manager; no network access."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from whisperx_studio import model_download


class ModelDownloadTests(unittest.TestCase):
    def make_snapshot(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "config.json").write_text("{}", encoding="utf-8")
        (root / "tokenizer.json").write_text("{}", encoding="utf-8")
        (root / "model.bin").write_bytes(b"x" * (1024 * 1024 + 1))
        return root

    def test_cached_tiny_model_is_verified_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_snapshot(Path(temp))
            with patch.object(model_download, "snapshot_download", return_value=str(root)) as snapshot:
                result = model_download.download("tiny")
            self.assertEqual(result, root)
            self.assertEqual(snapshot.call_count, 1)
            self.assertTrue(snapshot.call_args.kwargs["local_files_only"])

    def test_incomplete_cache_downloads_then_verifies_local_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_snapshot(Path(temp))
            calls = [RuntimeError("cache miss"), str(root), str(root)]
            with patch.object(model_download, "snapshot_download", side_effect=calls) as snapshot:
                result = model_download.download("small")
            self.assertEqual(result, root)
            self.assertEqual(snapshot.call_count, 3)
            self.assertFalse(snapshot.call_args_list[1].kwargs.get("local_files_only", False))
            self.assertTrue(snapshot.call_args_list[2].kwargs["local_files_only"])

    def test_status_detects_tiny_and_removal_deletes_only_its_repo_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            hub = Path(temp)
            with patch.object(model_download, "HF_HUB_CACHE", str(hub)), patch.dict(os.environ, {"WINWHISPER_DATA": ""}):
                tiny_root = model_download.cache_dir_for("tiny")
                snapshot = tiny_root / "snapshots" / "revision-a"
                self.make_snapshot(snapshot)
                other = hub / "models--Other--keep-me"
                other.mkdir()

                status = model_download.model_status("tiny")
                self.assertTrue(status["installed"])
                self.assertTrue(status["cached"])
                self.assertFalse(status["legacy"])
                # The UI reports one decimal place; 1 MiB + 1 byte rounds to 1.0.
                self.assertEqual(status["size_mb"], 1.0)

                self.assertTrue(model_download.remove("tiny"))
                self.assertFalse(tiny_root.exists())
                self.assertTrue(other.exists())
                self.assertFalse(model_download.model_status("tiny")["cached"])

    def test_partial_cache_can_be_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            hub = Path(temp)
            with patch.object(model_download, "HF_HUB_CACHE", str(hub)), patch.dict(os.environ, {"WINWHISPER_DATA": ""}):
                root = model_download.cache_dir_for("small")
                root.mkdir(parents=True)
                self.assertEqual(
                    model_download.model_status("small"),
                    {"installed": False, "cached": True, "legacy": False, "size_mb": 0.0},
                )
                self.assertTrue(model_download.remove("small"))
                self.assertFalse(root.exists())

    def test_legacy_shared_cache_is_detected_and_removed_with_native_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            native_hub = workspace / "models" / "huggingface-native" / "hub"
            legacy_hub = workspace / "models" / "huggingface" / "hub"
            with patch.object(model_download, "HF_HUB_CACHE", str(native_hub)), patch.dict(os.environ, {"WINWHISPER_DATA": str(workspace)}):
                native_root = model_download.cache_dir_for("tiny")
                legacy_root = model_download.legacy_cache_dir_for("tiny")
                self.assertIsNotNone(legacy_root)
                native_root.mkdir(parents=True)
                legacy_root.mkdir(parents=True)
                status = model_download.model_status("tiny")
                self.assertTrue(status["cached"])
                self.assertTrue(status["legacy"])
                self.assertTrue(model_download.remove("tiny"))
                self.assertFalse(native_root.exists())
                self.assertFalse(legacy_root.exists())

    def test_permission_error_names_broken_file_and_recovery_action(self):
        denied = PermissionError(13, "Access denied", r"C:\\cache\\vocabulary.txt")
        with patch.object(model_download, "snapshot_download", side_effect=denied):
            with self.assertRaises(RuntimeError) as raised:
                model_download.download("tiny")
        message = str(raised.exception)
        self.assertIn("vocabulary.txt", message)
        self.assertIn("entfernen", message)
        self.assertIn("getrennten Windows-Cache", message)

    def test_rejects_unknown_model(self):
        with self.assertRaises(ValueError):
            model_download.download("tiny; shell")
        with self.assertRaises(ValueError):
            model_download.remove("tiny; shell")


if __name__ == "__main__":
    unittest.main()
