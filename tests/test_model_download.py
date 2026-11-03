"""Unit tests for the verbose Whisper model downloader; no network access."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from whisperx_studio import model_download


class ModelDownloadTests(unittest.TestCase):
    def test_cached_tiny_model_is_verified_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.json").write_text("{}", encoding="utf-8")
            (root / "tokenizer.json").write_text("{}", encoding="utf-8")
            (root / "model.bin").write_bytes(b"x" * (1024 * 1024 + 1))
            with patch.object(model_download, "snapshot_download", return_value=str(root)) as snapshot:
                result = model_download.download("tiny")
            self.assertEqual(result, root)
            self.assertEqual(snapshot.call_count, 1)
            self.assertTrue(snapshot.call_args.kwargs["local_files_only"])

    def test_incomplete_cache_downloads_then_verifies_local_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.json").write_text("{}", encoding="utf-8")
            (root / "tokenizer.json").write_text("{}", encoding="utf-8")
            (root / "model.bin").write_bytes(b"x" * (1024 * 1024 + 1))
            calls = [RuntimeError("cache miss"), str(root), str(root)]
            with patch.object(model_download, "snapshot_download", side_effect=calls) as snapshot:
                result = model_download.download("small")
            self.assertEqual(result, root)
            self.assertEqual(snapshot.call_count, 3)
            self.assertFalse(snapshot.call_args_list[1].kwargs.get("local_files_only", False))
            self.assertTrue(snapshot.call_args_list[2].kwargs["local_files_only"])

    def test_rejects_unknown_model(self):
        with self.assertRaises(ValueError):
            model_download.download("tiny; shell")


if __name__ == "__main__":
    unittest.main()
