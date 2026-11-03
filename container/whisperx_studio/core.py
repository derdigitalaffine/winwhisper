"""Disk-backed audio and portable, non-destructive project documents.

Only a mono 16 kHz preview is decoded. Three hours require about 346 MB on disk,
and approximately 5 MB of waveform peaks, rather than a full in-memory buffer.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import wave

import numpy as np

DATA = Path.home() / ".local/share/local-ai/whisperx-studio"
RATE = 16000
PEAK_HZ = 100


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def clock(seconds, decimals=False):
    seconds = max(0, float(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return (
        f"{int(h):02d}:{int(m):02d}:{s:06.3f}"
        if decimals
        else f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
    )


def parse_clock(text):
    parts = str(text).strip().replace(",", ".").split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Zeit als Sekunden oder hh:mm:ss eingeben.")
    values = [float(x) for x in parts]
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("Die Zeit muss eine positive, endliche Zahl sein.")
    return sum(x * 60**i for i, x in enumerate(reversed(values)))


def run_media(command, cancel=None, progress=None):
    # A file prevents a full stderr pipe from deadlocking long FFmpeg jobs.
    with tempfile.TemporaryFile() as diagnostics:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=diagnostics,
        )
        try:
            while True:
                try:
                    code = proc.wait(timeout=0.15)
                    break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("Abgebrochen")
                    if progress:
                        progress()
            if code:
                diagnostics.seek(0)
                raise RuntimeError(
                    diagnostics.read().decode("utf-8", "replace")[-3500:]
                    or "Audioverarbeitung fehlgeschlagen"
                )
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def decode_audio(source, target, cancel=None):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError("Original und Arbeitskopie dürfen nicht dieselbe Datei sein.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.stem + ".part.wav")
    try:
        run_media(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(RATE),
                "-c:a",
                "pcm_s16le",
                str(temp),
            ],
            cancel,
        )
        with wave.open(str(temp)) as f:
            duration = f.getnframes() / f.getframerate()
        if duration <= 0:
            raise ValueError("Die Datei enthält keine Audiodaten.")
        os.replace(temp, target)
        return duration
    finally:
        temp.unlink(missing_ok=True)


def read_peaks(path, cancel=None):
    blocks = []
    with wave.open(str(path)) as f:
        step = f.getframerate() // PEAK_HZ
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("Abgebrochen")
            raw = f.readframes(step * 1000)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            padding = (-len(samples)) % step
            if padding:
                samples = np.pad(samples, (0, padding))
            blocks.append(np.max(np.abs(samples.reshape(-1, step)), axis=1) / 32768)
    return np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)


class AudioEdit:
    def __init__(self, source, duration, preview, spans=None):
        self.source = Path(source).resolve()
        self.original_duration = float(duration)
        if not math.isfinite(self.original_duration) or self.original_duration <= 0:
            raise ValueError("Ungültige Audiodauer im Projekt.")
        self.preview = Path(preview).resolve()
        self.spans = [
            (float(a), float(b))
            for a, b in (spans if spans is not None else [(0, duration)])
        ]
        if (
            not self.spans
            or any(
                not (
                    math.isfinite(a)
                    and math.isfinite(b)
                    and 0 <= a < b <= self.original_duration + 0.01
                )
                for a, b in self.spans
            )
            or any(
                a < previous[1] for previous, (a, b) in zip(self.spans, self.spans[1:])
            )
        ):
            raise ValueError("Ungültige Schnittbereiche im Projekt.")

    @property
    def duration(self):
        return sum(b - a for a, b in self.spans)

    def ranges(self, start=0, end=None):
        """Map a selection on the edited timeline back to original intervals."""
        end = self.duration if end is None else min(self.duration, end)
        start = max(0, start)
        result, offset = [], 0.0
        for a, b in self.spans:
            length = b - a
            left, right = max(start, offset), min(end, offset + length)
            if right > left:
                result.append((a + left - offset, a + right - offset))
            offset += length
        return result

    def remove(self, start, end):
        if not 0 <= start < end <= self.duration + 1e-6:
            raise ValueError("Bitte einen gültigen Bereich markieren.")
        spans = self.ranges(0, start) + self.ranges(end)
        if sum(b - a for a, b in spans) < 0.1:
            raise ValueError("Mindestens 0,1 Sekunden Audio müssen erhalten bleiben.")
        self.spans = spans

    def trim(self, start, end):
        if not 0 <= start < end <= self.duration + 1e-6 or end - start < 0.1:
            raise ValueError("Bitte mindestens 0,1 Sekunden markieren.")
        self.spans = self.ranges(start, end)

    def pixel_peaks(self, peaks, start, end, width):
        result = np.zeros(width, dtype=np.float32)
        if end <= start or not len(peaks):
            return result
        offset = 0.0
        for a, b in self.spans:
            length = b - a
            left, right = max(start, offset), min(end, offset + length)
            if right > left:
                x0 = max(0, int((left - start) / (end - start) * width))
                x1 = min(
                    width,
                    max(x0 + 1, math.ceil((right - start) / (end - start) * width)),
                )
                for x in range(x0, x1):
                    t0 = max(left, start + x / width * (end - start))
                    t1 = min(right, start + (x + 1) / width * (end - start))
                    i = max(0, int((a + t0 - offset) * PEAK_HZ))
                    j = min(
                        len(peaks), max(i + 1, math.ceil((a + t1 - offset) * PEAK_HZ))
                    )
                    if i < j:
                        result[x] = max(result[x], float(np.max(peaks[i:j])))
            offset += length
        return result

    def render(self, target, original_quality=False, cancel=None):
        target = Path(target).resolve()
        if target in (self.source, self.preview):
            raise ValueError(
                "Das Original und die Arbeitskopie werden nicht überschrieben."
            )
        if original_quality:
            filters = []
            for i, (a, b) in enumerate(self.spans):
                filters.append(
                    f"[0:a:0]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS[a{i}]"
                )
            inputs = "".join(f"[a{i}]" for i in range(len(self.spans)))
            filters.append(f"{inputs}concat=n={len(self.spans)}:v=0:a=1[out]")
            temp = target.with_name(target.stem + "." + uuid.uuid4().hex + ".part.wav")
            try:
                run_media(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(self.source),
                        "-filter_complex",
                        ";".join(filters),
                        "-map",
                        "[out]",
                        "-c:a",
                        "pcm_s16le",
                        str(temp),
                    ],
                    cancel,
                )
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        else:
            # Copy bounded blocks from the preview; no concatenation in RAM.
            temp = target.with_name(target.name + ".part")
            try:
                with (
                    wave.open(str(self.preview), "rb") as src,
                    wave.open(str(temp), "wb") as dest,
                ):
                    dest.setparams(src.getparams())
                    for a, b in self.spans:
                        first, last = round(a * RATE), round(b * RATE)
                        src.setpos(min(first, src.getnframes()))
                        remaining = last - first
                        while remaining > 0:
                            if cancel is not None and cancel.is_set():
                                raise InterruptedError("Abgebrochen")
                            frames = src.readframes(min(RATE * 10, remaining))
                            if not frames:
                                break
                            dest.writeframesraw(frames)
                            remaining -= len(frames) // 2
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        return target


def transcript_segments(data):
    if not isinstance(data, dict) or not isinstance(data.get("segments", []), list):
        raise ValueError("Das Transkript muss eine Liste von Abschnitten enthalten.")
    result = []
    for index, item in enumerate(data.get("segments", [])):
        if not isinstance(item, dict):
            raise ValueError("Das Transkript enthält einen ungültigen Abschnitt.")
        try:
            start, end = (
                float(item.get("start", 0)),
                float(item.get("end", item.get("start", 0))),
            )
        except (TypeError, ValueError):
            raise ValueError("Das Transkript enthält ungültige Zeitmarken.") from None
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end:
            raise ValueError("Das Transkript enthält ungültige Zeitmarken.")
        segment = copy.deepcopy(item)
        segment.update(
            id=f"s{index + 1:05d}",
            start=start,
            end=end,
            text=str(item.get("text", "")).strip(),
            speaker=str(item.get("speaker") or "UNBEKANNT"),
        )
        result.append(segment)
    return result


def fingerprint(project):
    keys = ("source", "spans", "segments", "speakers", "title", "date", "context")
    raw = json.dumps(
        {k: project.get(k) for k in keys}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def new_project(source, duration, preview, directory):
    source = Path(source).resolve()
    return {
        "format": "whisperx-studio",
        "version": 1,
        "source": str(source),
        "source_size": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns,
        "duration": duration,
        "preview": str(preview),
        "directory": str(directory),
        "spans": [[0.0, duration]],
        "title": source.stem,
        "date": dt.date.today().isoformat(),
        "context": "",
        "speakers": {},
        "segments": [],
        "reports": [],
        "created": dt.datetime.now().isoformat(timespec="seconds"),
    }


def load_project(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("format") != "whisperx-studio"
        or data.get("version") != 1
    ):
        raise ValueError("Keine unterstützte WhisperX-Studio-Projektdatei.")
    for key in ("source", "preview", "directory"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError("Im Projekt fehlt ein gültiger Dateipfad: " + key)
        value = Path(data[key])
        data[key] = str(
            value if value.is_absolute() else (path.parent / value).resolve()
        )
    source = Path(data["source"])
    if not source.is_file():
        raise ValueError(f"Die Originalaufnahme fehlt: {source}")
    if source.stat().st_size != data.get(
        "source_size"
    ) or source.stat().st_mtime_ns != data.get("source_mtime_ns"):
        raise ValueError(
            "Die Originaldatei wurde seit der Projekterstellung verändert. Bitte als neue Datei importieren."
        )
    try:
        AudioEdit(source, data["duration"], data["preview"], data["spans"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError(
            "Das Projekt enthält ungültige Audiodaten oder Schnittbereiche."
        ) from None
    data["segments"] = transcript_segments(data)
    if not isinstance(data.get("speakers", {}), dict) or any(
        not isinstance(v, str) for v in data.get("speakers", {}).values()
    ):
        raise ValueError("Das Projekt enthält ungültige Sprecherangaben.")
    reports = data.get("reports", [])
    if not isinstance(reports, list) or any(
        not isinstance(r, dict) or not isinstance(r.get("markdown"), str)
        for r in reports
    ):
        raise ValueError("Das Projekt enthält beschädigte Auswertungen.")
    if not isinstance(data.get("undo", []), list) or any(
        not isinstance(v, str) for v in data.get("undo", [])
    ):
        raise ValueError("Der Schnittverlauf im Projekt ist beschädigt.")
    for key in ("title", "date", "context"):
        if not isinstance(data.get(key, ""), str):
            raise ValueError("Das Projekt enthält ungültige Sitzungsangaben.")
    data.setdefault("reports", [])
    data.setdefault("speakers", {})
    return data
