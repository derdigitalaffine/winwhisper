"""Run with the private WhisperX Python: -m unittest whisperx_studio.test_core."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import numpy as np

from .core import AudioEdit, RATE, atomic_json, decode_audio, fingerprint, load_project, new_project, parse_clock, read_peaks, transcript_segments
from .analysis import SCHEMA, OllamaClient, chunk_segments, generate, is_local_model, validate_extract


def extraction(text="Anna erstellt den Bericht.", owner="Anna", due="morgen"):
    return {"summary": [{"text": "Ein Bericht wurde beauftragt.", "sources": ["s00001"]}],
            "topics": [{"title": "Bericht", "text": "Anna erläuterte den Vorschlag. Die Beteiligten besprachen die Umsetzung.", "sources": ["s00001"]}],
            "decisions": [], "votes": [], "open_questions": [],
            "tasks": [{"text": text, "owner": owner, "owner_evidence": "Anna erstellt den Bericht morgen.", "due": due,
                       "due_evidence": "morgen", "evidence": "Anna erstellt den Bericht morgen.", "sources": ["s00001"]}]}


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "Original mit Leerzeichen.wav"
        with wave.open(str(self.source), "wb") as f:
            f.setnchannels(2)
            f.setsampwidth(2)
            f.setframerate(48000)
            data = np.concatenate([np.full((48000, 2), n, dtype="<i2") for n in (1000, 2000, 3000, 4000)])
            f.writeframes(data.tobytes())
        self.preview = self.root / "preview.wav"
        self.duration = decode_audio(self.source, self.preview)
        self.doc = AudioEdit(self.source, self.duration, self.preview)
        self.original_bytes = self.source.read_bytes()

    def tearDown(self):
        self.assertEqual(self.original_bytes, self.source.read_bytes())
        self.temp.cleanup()

    def test_import_peaks_and_bounded_waveform(self):
        self.assertAlmostEqual(self.duration, 4)
        peaks = read_peaks(self.preview)
        self.assertEqual(len(peaks), 400)
        self.assertEqual(len(self.doc.pixel_peaks(peaks, 0, 4, 900)), 900)
        self.assertAlmostEqual(float(peaks[50]), 1000 / 32768, places=3)

    def test_multiple_cuts_map_back_to_original(self):
        self.doc.remove(1, 2)
        self.assertEqual(self.doc.spans, [(0., 1.), (2., 4.)])
        self.doc.remove(.5, 1.5)
        self.assertEqual(self.doc.spans, [(0., .5), (2.5, 4.)])
        self.doc.trim(.25, 1.25)
        self.assertEqual(self.doc.spans, [(.25, .5), (2.5, 3.25)])
        self.assertEqual(self.doc.duration, 1)

    def test_working_audio_content_and_timing(self):
        self.doc.remove(1, 3)
        output = self.doc.render(self.root / "working.wav")
        with wave.open(str(output)) as f:
            self.assertEqual(f.getnframes(), 2 * RATE)
            values = np.frombuffer(f.readframes(2 * RATE), dtype="<i2")
        self.assertAlmostEqual(float(np.median(values[:RATE])), 1000, delta=2)
        self.assertAlmostEqual(float(np.median(values[RATE:])), 4000, delta=2)

    def test_export_keeps_source_rate_channels_and_original(self):
        self.doc.remove(1, 3)
        output = self.doc.render(self.root / "Export mit Leerzeichen.wav", original_quality=True)
        with wave.open(str(output)) as f:
            self.assertEqual((f.getnchannels(), f.getframerate(), f.getnframes()), (2, 48000, 96000))
            values = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").reshape(-1, 2)
        np.testing.assert_array_equal(values[:48000], 1000)
        np.testing.assert_array_equal(values[48000:], 4000)

    def test_external_mp3_import(self):
        mp3 = self.root / "Externe Datei.mp3"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.source), str(mp3)], check=True)
        preview = self.root / "mp3-preview.wav"
        self.assertAlmostEqual(decode_audio(mp3, preview), 4, delta=.05)
        self.assertGreater(len(read_peaks(preview)), 390)

    def test_original_cannot_be_overwritten(self):
        for target in (self.source, self.preview):
            with self.assertRaises(ValueError):
                self.doc.render(target)
        with self.assertRaises(ValueError):
            decode_audio(self.source, self.source)

    def test_empty_cut_and_invalid_ranges_rejected(self):
        for selection in ((0, 4), (-1, 2), (2, 1), (0, 4.1)):
            with self.assertRaises(ValueError):
                self.doc.remove(*selection)
        for spans in ([], [(0, float("nan"))], [(-1, 3)], [(0, 10)]):
            with self.assertRaises(ValueError):
                AudioEdit(self.source, 4, self.preview, spans)

    def test_cancelled_render_leaves_no_output(self):
        cancel = threading.Event()
        cancel.set()
        target = self.root / "cancelled.wav"
        with self.assertRaises(InterruptedError):
            self.doc.render(target, cancel=cancel)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_project_roundtrip_and_modified_source_detection(self):
        project = new_project(self.source, 4, self.preview, self.root)
        project["spans"] = [[0, 1], [2, 4]]
        path = self.root / "project.whisperx.json"
        atomic_json(path, project)
        self.assertEqual(load_project(path)["spans"], project["spans"])
        stat = self.source.stat()
        import os
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 100))
        with self.assertRaisesRegex(ValueError, "verändert"):
            load_project(path)

    def test_three_hour_waveform_memory_and_mapping(self):
        doc = AudioEdit(self.source, 10800, self.preview)
        peaks = np.zeros(10800 * 100, dtype=np.float32)
        peaks[900000:900100] = .9
        doc.remove(100, 120)
        viewport = doc.pixel_peaks(peaks, 8979, 8982, 1200)
        self.assertLess(peaks.nbytes, 5_000_000)
        self.assertAlmostEqual(float(max(viewport)), .9, places=5)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.segments = transcript_segments({"segments": [{"start": 0, "end": 10, "speaker": "SPEAKER_00", "text": "Anna erstellt den Bericht morgen."},
                                                        {"start": 10, "end": 20, "speaker": "SPEAKER_01", "text": "Ich prüfe ihn anschließend."}]})
        self.aliases = {"SPEAKER_00": "Berta", "SPEAKER_01": "Claus"}

    def test_owner_and_person_speaking_are_distinct(self):
        clean, warnings = validate_extract(extraction(), self.segments, self.aliases)
        task = clean["tasks"][0]
        self.assertEqual(task["owner"], "Anna")
        self.assertEqual(task["said_by"], ["SPEAKER_00"])
        self.assertEqual(task["due"], "morgen")
        self.assertFalse(warnings)

    def test_unsupported_owner_and_due_are_open(self):
        clean, warnings = validate_extract(extraction(owner="Claus", due="2026-11-04"), self.segments, self.aliases)
        self.assertEqual(clean["tasks"][0]["owner"], "")
        self.assertEqual(clean["tasks"][0]["due"], "")
        self.assertEqual(len(warnings), 2)

    def test_self_commitment_uses_named_speaker(self):
        raw = extraction()
        raw["tasks"] = [{"text": "Bericht prüfen", "owner": "Claus", "owner_evidence": "Ich prüfe ihn anschließend.",
                         "due": "", "due_evidence": "", "evidence": "Ich prüfe ihn anschließend.", "sources": ["s00002"]}]
        clean, _ = validate_extract(raw, self.segments, self.aliases)
        self.assertEqual(clean["tasks"][0]["owner"], "Claus")
        self.assertEqual(clean["tasks"][0]["said_by"], ["SPEAKER_01"])

    def test_fabricated_references_and_evidence_are_rejected(self):
        raw = extraction()
        raw["topics"][0]["sources"] = ["s99999"]
        raw["tasks"][0]["evidence"] = "Das wurde nie gesagt."
        clean, warnings = validate_extract(raw, self.segments, self.aliases)
        self.assertFalse(clean["topics"])
        self.assertFalse(clean["tasks"])
        self.assertEqual(len(warnings), 2)

    def test_long_meeting_is_bounded_and_all_text_is_preserved(self):
        segments = transcript_segments({"segments": [{"start": i * 20, "end": (i + 1) * 20, "speaker": f"SPEAKER_{i % 15:02d}", "text": f"Beitrag {i}. " + "Gesprächsinhalt. " * 25} for i in range(540)]})
        chunks = chunk_segments(segments)
        self.assertGreater(len(chunks), 50)
        self.assertEqual([s["id"] for c in chunks for s in c], [s["id"] for s in segments])
        self.assertTrue(all(sum(len(s["text"]) + len(s["speaker"]) + 100 for s in c) <= 4200 for c in chunks))
        long = {**segments[0], "text": "abc " * 10000}
        self.assertEqual("".join(s["text"] for c in chunk_segments([long]) for s in c), long["text"])

    def test_resume_reuses_checkpoints_and_export_contains_sources(self):
        class FakeClient:
            calls = 0
            def check_model(self, model):
                pass
            def extract(self, model, text, context):
                self.calls += 1
                return extraction()
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            project = {"title": "Ratssitzung", "date": "2026-11-03", "context": "Haushalt", "segments": self.segments, "speakers": self.aliases}
            report = generate(project, "gemma4:e2b", directory, client=client)
            repeated = generate(project, "gemma4:e2b", directory, client=client)
            self.assertEqual(client.calls, 1)
            self.assertEqual(report["markdown"], repeated["markdown"])
            self.assertIn("## Ausführliches Protokoll", report["markdown"])
            self.assertIn("](#s00001)", report["markdown"])
            self.assertIn("### s00001", report["markdown"])
            self.assertIn("Zuständig: Anna", report["markdown"])
            self.assertIn("Erwähnt von: Berta", report["markdown"])
            project["segments"][0]["text"] += " Korrektur."
            self.assertNotEqual(report["fingerprint"], fingerprint(project))
            generate(project, "gemma4:e2b", directory, client=client)
            self.assertEqual(client.calls, 2)

    def test_only_local_gemma_qwen_are_allowed(self):
        for name in ("gemma4:e2b", "qwen3:14b-q4_K_M", "qwen2.5-coder:0.5b"):
            self.assertTrue(is_local_model(name))
        for name in ("qwen3:cloud", "gemma4-cloud", "https://example.com/gemma", "org/qwen3", "embeddinggemma"):
            self.assertFalse(is_local_model(name))

    def test_partial_interruption_resumes_at_first_unfinished_chunk(self):
        segments = [self.segments[0], {**self.segments[1], "start": 600, "end": 610}]
        class Client:
            calls = 0
            fail = True
            def check_model(self, model): pass
            def extract(self, model, text, context):
                self.calls += 1
                if self.calls == 2 and self.fail:
                    raise RuntimeError("Unterbrechung")
                ident = "s00002" if "s00002" in text else "s00001"
                data = {key: [] for key in SCHEMA["properties"]}
                data["topics"] = [{"title": "Thema", "text": "Ausführlicher Abschnitt.", "sources": [ident]}]
                return data
        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            project = {"segments": segments, "speakers": self.aliases}
            with self.assertRaisesRegex(RuntimeError, "Unterbrechung"):
                generate(project, "gemma4:e2b", directory, client=client)
            client.fail = False
            report = generate(project, "gemma4:e2b", directory, client=client)
            self.assertEqual(client.calls, 3)
            self.assertIn("### s00001", report["markdown"])
            self.assertIn("### s00002", report["markdown"])

    def test_truncated_output_is_retried_in_smaller_sections(self):
        class Client:
            calls = 0
            def check_model(self, model): pass
            def extract(self, model, text, context):
                self.calls += 1
                if "s00001" in text and "s00002" in text:
                    raise RuntimeError("Antwort am Ausgabelimit abgeschnitten")
                ident = "s00002" if "s00002" in text else "s00001"
                data = {key: [] for key in SCHEMA["properties"]}
                data["topics"] = [{"title": "Thema", "text": "Ausführlicher Abschnitt.", "sources": [ident]}]
                return data
        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            report = generate({"segments": self.segments, "speakers": self.aliases}, "gemma4:e2b", directory, client=client)
            self.assertEqual(client.calls, 3)
            self.assertIn("### s00001", report["markdown"])
            self.assertIn("### s00002", report["markdown"])

    def test_ollama_request_stays_on_loopback(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return b'{"models": [{"name": "gemma4:e2b"}, {"name": "qwen3:cloud"}]}'
        client = OllamaClient()
        with patch.object(client.opener, "open", return_value=Response()) as mock:
            self.assertEqual(client.models(), ["gemma4:e2b"])
            self.assertEqual(mock.call_args.args[0].full_url, "http://127.0.0.1:11434/api/tags")

    def test_transcript_and_time_validation(self):
        self.assertAlmostEqual(parse_clock("03:00:00.125"), 10800.125)
        for value in ("nan", "inf", "-1", "1:2:3:4"):
            with self.assertRaises(ValueError):
                parse_clock(value)
        with self.assertRaises(ValueError):
            transcript_segments({"segments": [{"start": float("nan"), "end": 20}]})


if __name__ == "__main__":
    unittest.main()
