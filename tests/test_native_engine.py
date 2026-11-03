"""Smoke tests for the installed native Windows AI stack.

These tests intentionally avoid model downloads. They verify the exact bridge
WinWhisper relies on: WhisperX decodes audio itself and passes pyannote an
in-memory waveform, so TorchCodec's optional file decoder is not required.
"""

from __future__ import annotations

import subprocess
import unittest

import imageio_ffmpeg
import numpy as np
import torch


class _EmptyDiarization:
    def itertracks(self, yield_label=False):
        return iter(())

    def labels(self):
        return []


class _Output:
    speaker_diarization = _EmptyDiarization()


class _CaptureModel:
    def __init__(self):
        self.audio = None

    def __call__(self, audio, **_kwargs):
        self.audio = audio
        return _Output()


class NativeEngineSmokeTests(unittest.TestCase):
    def test_private_ffmpeg_runs(self):
        executable = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [executable, "-version"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def test_engine_imports(self):
        import ctranslate2
        import faster_whisper
        import whisperx
        from pyannote.audio import Pipeline

        self.assertIsNotNone(ctranslate2)
        self.assertIsNotNone(faster_whisper)
        self.assertIsNotNone(whisperx)
        self.assertIsNotNone(Pipeline)

    def test_whisperx_diarization_uses_in_memory_waveform(self):
        from whisperx.diarize import DiarizationPipeline, SAMPLE_RATE

        capture = _CaptureModel()
        pipeline = DiarizationPipeline.__new__(DiarizationPipeline)
        pipeline.model = capture
        result = pipeline(np.zeros(SAMPLE_RATE // 10, dtype=np.float32))

        self.assertEqual(len(result), 0)
        self.assertIsInstance(capture.audio, dict)
        self.assertEqual(capture.audio["sample_rate"], SAMPLE_RATE)
        waveform = capture.audio["waveform"]
        self.assertIsInstance(waveform, torch.Tensor)
        self.assertEqual(tuple(waveform.shape), (1, SAMPLE_RATE // 10))


if __name__ == "__main__":
    unittest.main(verbosity=2)
