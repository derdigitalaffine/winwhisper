"""Private JSON-lines service for the Electron desktop. No HTTP server or Tk."""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
import wave

import numpy as np

from .analysis import OllamaClient, installed_models
from .core import (
    AudioEdit,
    DATA,
    atomic_json,
    clock,
    decode_audio,
    fingerprint,
    load_project,
    new_project,
    read_peaks,
    transcript_segments,
)
from .report_profiles import PROFILES

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / "whisperx-venv/bin/python"
CLI = Path.home() / ".local/bin/whisperx-local"


def guarded_command(command, death_signal=signal.SIGTERM):
    return [
        sys.executable,
        "-m",
        "whisperx_studio.process_guard",
        str(os.getpid()),
        str(int(death_signal)),
        *command,
    ]


class DesktopService:
    def __init__(self, emit=None):
        self._output_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self.emit = emit or self.write
        self.project = self.doc = self.project_path = None
        self.peaks = np.zeros(0, dtype=np.float32)
        self.busy = False
        self.operation = ""
        self.status = "Bereit für deine nächste Aufnahme."
        self.cancel_event = threading.Event()
        self.proc = self.record_proc = self.live_proc = None
        self.record_log = None
        self.record_path = None
        self.live_stop = None
        self.live_reader_thread = None
        self.live_segments = []
        self.closed = False
        self.models = installed_models()
        self.model_status = "Verbindung wird geprüft"
        self.mics = [{"name": "Standardmikrofon", "value": ""}]
        self.settings = {
            "language": "de",
            "asr_model": "small",
            "device": "auto",
            "diarize": False,
            "speaker_count": "auto",
            "microphone": "",
            "live": False,
            "finalize_live": True,
        }
        self.logs = []
        self.recent = self.read_recent()
        try:
            saved = json.loads((DATA / "settings.json").read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key, value in saved.items():
                    try:
                        self.validate_settings({key: value}, available_microphone=False)
                    except ValueError:
                        continue
                    if key in self.settings:
                        self.settings[key] = value
        except (OSError, ValueError):
            pass

    def write(self, kind, data):
        with self._output_lock:
            print(
                json.dumps(
                    {"type": kind, "data": data}, ensure_ascii=False, allow_nan=False
                ),
                flush=True,
            )

    def log(self, message):
        self.logs.append(str(message).rstrip())
        self.logs = self.logs[-350:]
        self.emit("log", str(message).rstrip())

    def read_recent(self):
        result = []
        try:
            paths = json.loads((DATA / "recent.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            paths = []
        if not isinstance(paths, list):
            paths = []
        for value in paths[:20]:
            try:
                path = Path(value)
                p = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(p, dict) or p.get("format") != "whisperx-studio":
                    continue
                result.append(
                    {
                        "path": str(path),
                        "title": p.get("title") or path.stem,
                        "date": p.get("date", ""),
                        "duration": p.get("duration", 0),
                    }
                )
            except (OSError, ValueError, TypeError):
                pass
        return result

    def state(self):
        with self._state_lock:
            return copy.deepcopy(self._state())

    def _state(self):
        p = self.project
        current = fingerprint(p) if p else ""
        reports = []
        for i, r in enumerate(p.get("reports", []) if p else []):
            reports.append(
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("sources", "speakers", "items", "tasks")
                }
            )
            reports[-1].update(
                index=i,
                stale=r.get("fingerprint") != current,
                kind=r.get("kind", "legacy"),
                label=r.get("label", "Frühere Gesamtauswertung"),
                created=str(r.get("created") or ""),
            )
        return {
            "busy": self.busy,
            "operation": self.operation,
            "status": self.status,
            "recording": self.record_proc is not None,
            "project": bool(p),
            "title": p.get("title", "Neue Aufnahme") if p else "Neue Aufnahme",
            "date": p.get("date", dt.date.today().isoformat())
            if p
            else dt.date.today().isoformat(),
            "context": p.get("context", "") if p else "",
            "file": self.doc.source.name if self.doc else "",
            "project_path": str(self.project_path or ""),
            "duration": self.doc.duration if self.doc else 0,
            "spans": self.doc.spans if self.doc else [],
            "audio_url": self.doc.preview.as_uri() if self.doc else "",
            "segments": [
                {k: s[k] for k in ("id", "start", "end", "text", "speaker")}
                for s in p.get("segments", [])
            ]
            if p
            else [],
            "speakers": p.get("speakers", {}) if p else {},
            "reports": reports,
            "can_undo": bool(p and p.get("undo")),
            "preliminary": bool(p and p.get("preliminary")),
            "models": self.models,
            "model_status": self.model_status,
            "microphones": self.mics,
            "settings": self.settings,
            "recent": self.recent,
            "profiles": [
                {"kind": key, **{k: v for k, v in value.items() if k != "instruction"}}
                for key, value in PROFILES.items()
            ],
        }

    def push(self):
        if not self.closed:
            self.emit("state", self.state())

    def save(self):
        if not self.project:
            return
        self.project["spans"] = [list(x) for x in self.doc.spans]
        canonical = Path(self.project["directory"]) / "project.whisperx.json"
        primary = self.project_path or canonical
        atomic_json(primary, self.project)
        if primary.resolve() != canonical.resolve():
            try:
                atomic_json(canonical, self.project)
            except OSError as exc:
                self.log(
                    f"Projekt unter {primary} gespeichert; interne Sicherung nicht aktualisiert: {exc}"
                )

    def remember(self):
        current = str(self.project_path)
        old = [r["path"] for r in self.recent if r["path"] != current]
        try:
            atomic_json(DATA / "recent.json", [current] + old[:19])
        except OSError as exc:
            self.log(
                "Projekt gespeichert; Liste zuletzt geöffneter Projekte konnte nicht aktualisiert werden: "
                + str(exc)
            )
            return
        self.recent = self.read_recent()

    def commit_project(self, candidate):
        with self._state_lock:
            if self.closed:
                raise InterruptedError()
            previous = self.project
            self.project = candidate
            try:
                self.save()
            except Exception:
                self.project = previous
                raise

    def unlocked(self):
        if self.busy or self.record_proc:
            raise ValueError(
                "Bitte die laufende Aufnahme oder Verarbeitung zuerst beenden."
            )

    def require_project(self):
        if not self.project:
            raise ValueError("Bitte zuerst eine Aufnahme oder ein Projekt öffnen.")

    def start_job(self, operation, work):
        self.unlocked()
        self.busy, self.operation = True, operation
        self.cancel_event = threading.Event()
        cancel = self.cancel_event
        self.push()

        def run():
            try:
                work(cancel)
            except InterruptedError:
                self.status = "Abgebrochen. Original und fertige Zwischenschritte bleiben erhalten."
            except Exception as exc:
                self.status = "Fehler: " + str(exc)[:500]
                self.log(str(exc))
                self.emit("error", str(exc))
            finally:
                self.busy, self.operation = False, ""
                self.proc = None
                self.push()

        threading.Thread(target=run, daemon=True).start()

    def activate(self, project, peaks, path=None):
        with self._state_lock:
            return self._activate(project, peaks, path)

    def _activate(self, project, peaks, path=None):
        if self.closed:
            raise InterruptedError()
        previous = self.project, self.doc, self.project_path, self.peaks
        self.project = project
        self.project_path = (
            Path(path) if path else Path(project["directory"]) / "project.whisperx.json"
        )
        self.doc = AudioEdit(
            project["source"], project["duration"], project["preview"], project["spans"]
        )
        self.peaks = peaks
        try:
            self.save()
        except Exception:
            self.project, self.doc, self.project_path, self.peaks = previous
            raise
        self.remember()
        self.emit("audio_changed", {"url": self.doc.preview.as_uri()})
        self.status = f"{clock(self.doc.duration)} geladen · Änderungen werden automatisch gespeichert."

    def load_audio_work(self, path, cancel, live_segments=None):
        source = Path(path).resolve()
        directory = (
            DATA
            / "projects"
            / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
        )
        preview = directory / "preview.wav"
        duration = decode_audio(source, preview, cancel)
        peaks = read_peaks(preview, cancel)
        if cancel.is_set():
            raise InterruptedError()
        p = new_project(source, duration, preview, directory)
        if live_segments:
            p["segments"] = transcript_segments({"segments": live_segments})
            p["preliminary"] = True
        self.activate(p, peaks)

    def run_process(self, command, cancel, on_line=None, secret=None):
        if cancel.is_set() or self.closed:
            raise InterruptedError()
        proc = subprocess.Popen(
            guarded_command(command),
            cwd=str(ROOT),
            stdin=subprocess.PIPE if secret is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        self.proc = proc
        # Monitor cancellation independently of stdout: a quiet GPU job must also stop.
        finished = threading.Event()

        def watch():
            while not finished.wait(0.1):
                if cancel.is_set() or self.closed:
                    self.stop_process(proc)
                    return

        threading.Thread(target=watch, daemon=True).start()
        try:
            if secret is not None:
                proc.stdin.write(secret)
                proc.stdin.close()
            for line in proc.stdout:
                if on_line:
                    on_line(line)
                else:
                    self.log(line)
            code = proc.wait()
        finally:
            finished.set()
            # A callback can fail (invalid JSON, disk full). Reap before unlocking.
            if proc.poll() is None:
                self.stop_process(proc)
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    stream.close()
            if self.proc is proc:
                self.proc = None
        if cancel.is_set():
            raise InterruptedError()
        if code:
            raise RuntimeError(
                "Verarbeitung fehlgeschlagen. Details im Aktivitätsprotokoll."
            )

    @staticmethod
    def stop_process(proc):
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return

            def force():
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

            timer = threading.Timer(3, force)
            timer.daemon = True
            timer.start()

    def transcribe_work(self, cancel):
        self.require_project()
        settings = dict(self.settings)
        self.status = "Audiofassung vorbereiten …"
        self.push()
        working = self.doc.render(
            Path(self.project["directory"]) / "working.wav", cancel=cancel
        )
        out = (
            Path.home()
            / "Dokumente/Transkripte"
            / (
                "Studio_"
                + dt.datetime.now().strftime("%Y%m%d-%H%M%S-")
                + uuid.uuid4().hex[:5]
            )
        )
        cmd = [
            str(CLI),
            str(working),
            "--model",
            settings["asr_model"],
            "--studio-performance",
            "--vad_method",
            "silero",
            "--output_dir",
            str(out),
        ]
        if settings["device"] == "auto":
            cmd.append("--studio-auto-device")
        else:
            cmd += ["--device", "cuda" if settings["device"] == "gpu" else "cpu"]
        if settings["language"] != "auto":
            cmd += ["--language", settings["language"]]
        if settings["diarize"]:
            cmd += [
                "--diarize",
                "--max_speakers",
                "15"
                if settings["speaker_count"] == "auto"
                else str(settings["speaker_count"]),
            ]
            if settings["speaker_count"] != "auto":
                cmd += ["--min_speakers", str(settings["speaker_count"])]
        self.status = "WhisperX transkribiert die Aufnahme …"
        self.push()
        self.run_process(cmd, cancel)
        files = sorted(out.glob("*.json"))
        if not files:
            raise ValueError("WhisperX hat kein JSON-Transkript erzeugt.")
        candidate = copy.deepcopy(self.project)
        candidate["segments"] = transcript_segments(
            json.loads(files[0].read_text(encoding="utf-8"))
        )
        candidate.pop("preliminary", None)
        if cancel.is_set():
            raise InterruptedError()
        self.commit_project(candidate)
        self.status = f"Transkript fertig · {len(self.project['segments'])} Abschnitte."

    def refresh_connections(self):
        if not self._refresh_lock.acquire(blocking=False):
            return

        def work():
            try:
                self._refresh_connections()
            finally:
                self._refresh_lock.release()

        threading.Thread(target=work, daemon=True).start()

    def _refresh_connections(self):
        try:
            self.models = OllamaClient().models()
            self.model_status = "Ollama verbunden"
        except Exception as exc:
            self.model_status = "Ollama nicht erreichbar"
            self.log(str(exc))
        try:
            proc = subprocess.run(
                ["pactl", "--format=json", "list", "sources"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            self.mics = [{"name": "Standardmikrofon", "value": ""}] + [
                {"name": s.get("description", s["name"]), "value": s["name"]}
                for s in json.loads(proc.stdout)
                if not s["name"].endswith(".monitor")
            ]
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            pass
        self.push()

    def ensure_preview(self, project, cancel):
        path = Path(project["preview"])
        try:
            with wave.open(str(path), "rb") as audio:
                valid = (
                    audio.getnchannels() == 1
                    and audio.getsampwidth() == 2
                    and audio.getframerate() == 16000
                    and abs(audio.getnframes() / 16000 - project["duration"]) < 0.01
                    and path.stat().st_size >= audio.getnframes() * 2
                )
        except (OSError, EOFError, wave.Error):
            valid = False
        if not valid:
            self.log(
                "Arbeitskopie fehlt oder ist beschädigt; sie wird aus der Originalaufnahme wiederhergestellt."
            )
            decode_audio(project["source"], path, cancel)

    def validate_settings(self, values, available_microphone=True):
        if not isinstance(values, dict):
            raise ValueError("Ungültige Einstellungen.")
        allowed = {
            "language": ["de", "en", "auto"],
            "asr_model": ["tiny", "base", "small", "medium", "large-v3"],
            "device": ["auto", "gpu", "cpu"],
            "speaker_count": ["auto"] + [str(x) for x in range(1, 16)],
        }
        for k, v in values.items():
            if k in allowed and str(v) not in allowed[k]:
                raise ValueError("Ungültige Einstellung: " + k)
            if k in ("diarize", "live", "finalize_live") and not isinstance(v, bool):
                raise ValueError("Ungültige Einstellung: " + k)
            if k == "microphone" and (
                not isinstance(v, str)
                or (available_microphone and v not in [m["value"] for m in self.mics])
            ):
                raise ValueError("Das Mikrofon ist nicht verfügbar.")

    def change_settings(self, values):
        self.unlocked()
        self.validate_settings(values)
        candidate = {
            **self.settings,
            **{k: v for k, v in values.items() if k in self.settings},
        }
        atomic_json(DATA / "settings.json", candidate)
        self.settings = candidate

    def start_recording(self):
        self.unlocked()
        self.save()
        directory = Path.home() / "Musik/WhisperX-Aufnahmen"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            "Aufnahme_"
            + dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-")
            + uuid.uuid4().hex[:6]
            + ".wav"
        )
        log = path.with_suffix(".log").open("w+")
        command = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]
        if self.settings["microphone"]:
            command += ["--target", self.settings["microphone"]]
        command.append(str(path))
        try:
            self.record_proc = subprocess.Popen(
                guarded_command(command, signal.SIGINT),
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log,
                start_new_session=True,
            )
        except Exception:
            log.close()
            raise
        self.record_path, self.record_log = path, log
        self.project = self.doc = self.project_path = None
        self.live_segments = []
        self.record_started = time.monotonic()
        self.status = "Mikrofonaufnahme läuft …"
        self.push()
        if self.settings["live"]:
            try:
                self.start_live(path)
            except (OSError, subprocess.SubprocessError) as exc:
                self.log(
                    "Live-Transkription konnte nicht starten; die Audioaufnahme läuft weiter: "
                    + str(exc)
                )
                self.emit(
                    "error",
                    "Live-Transkription nicht verfügbar. Die Audioaufnahme läuft weiter und kann anschließend transkribiert werden.",
                )
        threading.Thread(target=self.record_wave, daemon=True).start()

    def start_live(self, path):
        out = Path.home() / "Dokumente/Transkripte" / (path.stem + "_live")
        out.mkdir(parents=True, exist_ok=True)
        self.live_stop = out / "stop.signal"
        self.live_stop.unlink(missing_ok=True)
        self.live_proc = subprocess.Popen(
            guarded_command(
                [
                    str(CLI),
                    "--live",
                    "--audio",
                    str(path),
                    "--output",
                    str(out),
                    "--stop-file",
                    str(self.live_stop),
                    "--language",
                    self.settings["language"],
                ]
            ),
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        live_proc = self.live_proc

        def live_reader():
            for line in live_proc.stdout:
                try:
                    event = json.loads(line)
                    if event.get("type") == "partial":
                        self.live_segments.append(
                            {
                                k: event[k]
                                for k in ("start", "end", "text", "words")
                                if k in event
                            }
                        )
                        self.emit("live", event)
                    elif event.get("type") == "error":
                        self.log(event.get("message", "Live-Fehler"))
                except (ValueError, TypeError, AttributeError):
                    self.log(line)

        self.live_reader_thread = threading.Thread(target=live_reader, daemon=True)
        self.live_reader_thread.start()

    def record_wave(self):
        proc, path = self.record_proc, self.record_path
        if proc is None:
            return
        offset, frames, blocks = None, 0, []
        while self.record_proc is proc and proc.poll() is None and not self.closed:
            try:
                with path.open("rb") as f:
                    if offset is None:
                        header = f.read(12)
                        if header[:4] == b"RIFF" and header[8:] == b"WAVE":
                            for _ in range(64):
                                raw = f.read(8)
                                if len(raw) < 8:
                                    break
                                name, length = struct.unpack("<4sI", raw)
                                if name == b"data":
                                    offset = f.tell()
                                    break
                                if length > 65536:
                                    break
                                f.seek(length + length % 2, 1)
                    if offset is not None:
                        f.seek(offset + frames * 2)
                        raw = f.read(16000 * 2 * 3)
                        count = len(raw) // 320 * 320
                        if count:
                            samples = (
                                np.frombuffer(raw[:count], dtype="<i2")
                                .astype(np.float32)
                                .reshape(-1, 160)
                            )
                            blocks.append(np.max(np.abs(samples), axis=1) / 32768)
                            frames += count // 2
                peaks = (
                    np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
                )
                if len(peaks):
                    count = min(1400, len(peaks))
                    edges = np.linspace(0, len(peaks), count + 1, dtype=int)
                    preview = [
                        float(np.max(peaks[a:b])) for a, b in zip(edges[:-1], edges[1:])
                    ]
                else:
                    preview = []
                self.emit(
                    "record_wave",
                    {
                        "elapsed": time.monotonic() - self.record_started,
                        "peaks": preview,
                    },
                )
            except (OSError, ValueError):
                pass
            time.sleep(0.3)
        if self.record_proc is proc and not self.closed:
            self.log("Die Mikrofonaufnahme wurde unerwartet beendet.")
            self.stop_recording()

    def stop_recording(self):
        proc = self.record_proc
        if not proc:
            return
        self.record_proc = None
        self.busy, self.operation = True, "Aufnahme speichern"
        self.cancel_event = threading.Event()
        self.push()

        def work():
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                if self.record_log:
                    self.record_log.flush()
                    self.record_log.seek(0)
                    diagnostics = self.record_log.read()
                    self.record_log.close()
                    self.record_log = None
                    if diagnostics:
                        self.log(diagnostics)
                if self.live_proc:
                    self.live_stop.touch()
                    self.status = "Letzte Live-Wörter werden verarbeitet …"
                    self.push()
                    try:
                        self.live_proc.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        self.stop_process(self.live_proc)
                        self.log(
                            "Live-Abschluss dauerte zu lange; die Originalaufnahme bleibt erhalten."
                        )
                    if self.live_reader_thread:
                        self.live_reader_thread.join(timeout=4)
                    self.live_proc = None
                    self.live_reader_thread = None
                self.load_audio_work(
                    self.record_path, self.cancel_event, list(self.live_segments)
                )
                if (
                    self.settings["live"]
                    and self.settings["finalize_live"]
                    and not self.cancel_event.is_set()
                ):
                    self.transcribe_work(self.cancel_event)
            except InterruptedError:
                self.status = (
                    "Verarbeitung abgebrochen. Die Originalaufnahme bleibt erhalten."
                )
            except Exception as exc:
                self.log(str(exc))
                self.status = "Aufnahme konnte nicht geladen werden: " + str(exc)[:300]
                self.emit("error", self.status)
            finally:
                self.busy, self.operation = False, ""
                self.push()

        threading.Thread(target=work, daemon=True).start()

    def destination(self, path):
        dest = Path(path).expanduser().resolve()
        if self.project:
            protected = {
                self.doc.source,
                self.doc.preview,
                self.project_path.resolve(),
                Path(self.project["directory"]).resolve() / "project.whisperx.json",
            }
            if dest in protected:
                raise ValueError(
                    "Original, Arbeitskopie und Projekt werden nicht überschrieben."
                )
        return dest

    def generate_work(self, payload, cancel):
        self.require_project()
        if not self.project.get("segments"):
            raise ValueError(
                "Bitte zuerst transkribieren oder ein Transkript importieren."
            )
        kind = payload.get("kind")
        if kind not in PROFILES:
            raise ValueError("Bitte eine Auswertungsart auswählen.")
        models = payload.get("models", [])
        if not 1 <= len(models) <= 2 or any(m not in self.models for m in models):
            raise ValueError("Bitte ein lokal installiertes Modell auswählen.")
        models = list(dict.fromkeys(models))
        run = Path(self.project["directory"]) / "runs" / uuid.uuid4().hex
        p = copy.deepcopy(self.project)
        p["requested_report"] = {
            "kind": kind,
            "options": payload.get("options", {}),
            "group": run.name,
        }
        atomic_json(run / "input.json", p)
        error = []

        def line(raw):
            try:
                e = json.loads(raw)
            except ValueError:
                self.log(raw)
                return
            if e.get("type") == "progress":
                v = e["data"]
                self.status = f"{PROFILES[kind]['label']} · {v['model']} · Abschnitt {v['current']}/{v['total']}"
                self.emit(
                    "progress",
                    {"text": self.status, "current": v["current"], "total": v["total"]},
                )
            elif e.get("type") == "phase":
                self.status = e["data"]["text"]
                self.emit("progress", {"text": self.status})
            elif e.get("type") == "report":
                r = json.loads(Path(e["data"]).read_text(encoding="utf-8"))
                if (
                    not isinstance(r, dict)
                    or r.get("kind") != kind
                    or not isinstance(r.get("markdown"), str)
                ):
                    raise ValueError(
                        "Der Auswertungsdienst lieferte kein gültiges Dokument."
                    )
                r["group"] = run.name
                candidate = copy.deepcopy(self.project)
                candidate.setdefault("reports", []).append(r)
                self.commit_project(candidate)
                self.push()
                self.emit(
                    "report_ready",
                    {
                        "index": len(self.project["reports"]) - 1,
                        "kind": kind,
                        "model": r["model"],
                    },
                )
            elif e.get("type") == "diagnostic":
                self.log(e["data"])
            elif e.get("type") == "error":
                error.append(str(e["data"]))
                self.log(e["data"])

        self.status = "Lokales Modell wird geladen …"
        self.push()
        try:
            self.run_process(
                [
                    str(PYTHON),
                    "-m",
                    "whisperx_studio.worker",
                    str(run / "input.json"),
                    *models,
                ],
                cancel,
                line,
            )
        except RuntimeError:
            raise RuntimeError(
                error[-1]
                if error
                else "Die Auswertung ist fehlgeschlagen. Details im Aktivitätsprotokoll."
            )
        self.status = PROFILES[kind]["label"] + " fertig."

    def command(self, action, data):
        transactional = {
            "metadata",
            "update_segment",
            "speakers",
            "cut",
            "trim",
            "undo",
            "save_as",
            "import_transcript",
        }
        if action not in transactional:
            return self._command(action, data)
        with self._state_lock:
            self.unlocked()
            previous = copy.deepcopy(self.project), self.doc, self.project_path
            try:
                return self._command(action, data)
            except Exception:
                self.project, self.doc, self.project_path = previous
                raise

    def _command(self, action, data):
        if action == "init":
            self.push()
            self.refresh_connections()
            return True
        if action == "refresh":
            self.refresh_connections()
            return True
        if action == "logs":
            return self.logs
        if action == "cancel":
            self.cancel_event.set()
            self.stop_process(self.proc)
            self.stop_process(self.live_proc)
            self.status = "Wird abgebrochen …"
            self.push()
            return True
        if action == "record_start":
            self.start_recording()
            return True
        if action == "record_stop":
            self.stop_recording()
            return True
        if action == "shutdown":
            self.closed = True
            self.cancel_event.set()
            self.stop_process(self.proc)
            self.stop_process(self.live_proc)
            if self.record_proc and self.record_proc.poll() is None:
                self.record_proc.send_signal(signal.SIGINT)
                try:
                    self.record_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.record_proc.kill()
            self.save()
            return True
        if action == "waveform":
            if not self.doc:
                return []
            return self.doc.pixel_peaks(
                self.peaks,
                max(0.0, float(data.get("start", 0))),
                min(self.doc.duration, float(data.get("end", self.doc.duration))),
                max(1, min(2200, int(data.get("width", 1400)))),
            ).tolist()
        self.unlocked()
        if action == "settings":
            self.change_settings(data)
        elif action == "load_audio":
            self.save()
            self.status = "Audio und Waveform werden geladen …"
            self.start_job(
                "Audio laden", lambda cancel: self.load_audio_work(data["path"], cancel)
            )
        elif action == "open_project":
            self.save()

            def load(cancel):
                p = load_project(data["path"])
                self.ensure_preview(p, cancel)
                peaks = read_peaks(p["preview"], cancel)
                if cancel.is_set():
                    raise InterruptedError()
                self.activate(p, peaks, data["path"])

            self.status = "Projekt wird geöffnet …"
            self.start_job("Projekt öffnen", load)
        elif action == "transcribe":
            self.require_project()
            self.start_job("Transkribieren", self.transcribe_work)
        elif action == "generate":
            self.start_job(
                "Auswertung erstellen", lambda cancel: self.generate_work(data, cancel)
            )
        elif action == "setup_speakers":
            secret = str(data.get("token", "")).strip()
            if not secret.startswith("hf_"):
                raise ValueError(
                    "Bitte einen gültigen Hugging-Face-Read-Token eingeben."
                )
            code = "import sys,subprocess; from huggingface_hub import login; login(token=sys.stdin.read().strip(),add_to_git_credential=False); sys.exit(subprocess.call([sys.argv[1],'--setup-speakers']))"
            self.status = "Sprechermodell wird eingerichtet …"
            self.start_job(
                "Sprecher einrichten",
                lambda cancel: self.run_process(
                    [str(PYTHON), "-c", code, str(CLI)], cancel, secret=secret
                ),
            )
        else:
            self.require_project()
            if action == "metadata":
                for key in ("title", "date", "context"):
                    if key in data:
                        self.project[key] = str(data[key])[:5000]
                self.save()
            elif action == "update_segment":
                segment = next(
                    (s for s in self.project["segments"] if s["id"] == data["id"]), None
                )
                if not segment:
                    raise ValueError("Der Abschnitt ist nicht mehr vorhanden.")
                if "text" in data and data["text"].strip() != segment["text"]:
                    segment.setdefault("original_text", segment["text"])
                    segment["text"] = str(data["text"]).strip()
                    segment["text_edited"] = True
                    segment.pop("words", None)
                if "speaker" in data:
                    allowed = (
                        set(self.project.get("speakers", {}))
                        | {s["speaker"] for s in self.project["segments"]}
                        | {"UNBEKANNT"}
                    )
                    if data["speaker"] not in allowed:
                        raise ValueError("Bitte einen vorhandenen Sprecher wählen.")
                    segment["speaker"] = data["speaker"]
                self.save()
            elif action == "speakers":
                self.project["speakers"] = {
                    str(k): str(v).strip() or str(k)
                    for k, v in data.get("names", {}).items()
                }
                self.save()
            elif action in ("cut", "trim"):
                edited = AudioEdit(
                    self.doc.source,
                    self.doc.original_duration,
                    self.doc.preview,
                    self.doc.spans,
                )
                getattr(edited, "remove" if action == "cut" else "trim")(
                    float(data["start"]), float(data["end"])
                )
                if edited.spans != self.doc.spans:
                    previous = (
                        Path(self.project["directory"])
                        / "history"
                        / (uuid.uuid4().hex + ".json")
                    )
                    atomic_json(previous, self.project)
                    self.project["undo"] = (
                        self.project.get("undo", []) + [str(previous)]
                    )[-30:]
                    self.doc = edited
                    self.project["segments"] = []
                    self.save()
                    self.emit("audio_changed", {"url": self.doc.preview.as_uri()})
                    self.status = "Schnitt gespeichert. Für die geänderte Zeitachse neu transkribieren; Rückgängig stellt auch das Transkript wieder her."
            elif action == "undo":
                history = self.project.get("undo", [])
                if history:
                    previous = load_project(history[-1])
                    for key in ("title", "date", "context"):
                        previous[key] = self.project.get(key, previous.get(key, ""))
                    for report in self.project.get("reports", []):
                        if report not in previous.setdefault("reports", []):
                            previous["reports"].append(report)
                    self.project = previous
                    self.doc = AudioEdit(
                        self.project["source"],
                        self.project["duration"],
                        self.project["preview"],
                        self.project["spans"],
                    )
                    self.save()
                    self.emit("audio_changed", {"url": self.doc.preview.as_uri()})
                    self.status = "Schnitt rückgängig gemacht."
            elif action == "save_as":
                destination = self.destination(data["path"])
                atomic_json(destination, self.project)
                self.project_path = destination
                self.remember()
                self.status = "Projekt gespeichert."
            elif action == "import_transcript":
                segments = transcript_segments(
                    json.loads(Path(data["path"]).read_text(encoding="utf-8"))
                )
                if segments and max(s["end"] for s in segments) > self.doc.duration + 1:
                    raise ValueError(
                        "Die Zeitmarken reichen über die Audiofassung hinaus."
                    )
                self.project["segments"] = segments
                self.save()
                self.status = f"{len(segments)} Abschnitte importiert. Bitte die Zuordnung zur Audiofassung prüfen."
            elif action == "export_audio":
                dest = self.destination(data["path"])
                self.status = "Audiofassung wird exportiert …"
                self.start_job(
                    "Audio exportieren",
                    lambda cancel: self.doc.render(
                        dest, original_quality=True, cancel=cancel
                    ),
                )
            elif action in ("export_report", "export_transcript"):
                dest = self.destination(data["path"])
                if action == "export_report":
                    report = self.project["reports"][int(data["index"])]
                    text = report["markdown"]
                    if not report.get("options", {}).get("include_sources", True):
                        import re

                        text = re.sub(r"\[([^\]]+)\]\(#s\d+\)", r"\1", text)
                    if report.get("fingerprint") != fingerprint(self.project):
                        text = (
                            "> ÄLTERER STAND: Das Transkript oder die Sitzungsangaben wurden inzwischen geändert.\n\n"
                            + text
                        )
                else:
                    lines = ["# " + self.project["title"], "", "## Transkript", ""]
                    names = self.project.get("speakers", {})
                    for s in self.project["segments"]:
                        lines += [
                            f"### {clock(s['start'])} · {names.get(s['speaker'], s['speaker'])}",
                            "",
                            s["text"],
                            "",
                        ]
                    text = "\n".join(lines)
                temporary = dest.with_name(dest.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    temporary.write_text(text, encoding="utf-8")
                    os.replace(temporary, dest)
                finally:
                    temporary.unlink(missing_ok=True)
                self.status = "Markdown exportiert: " + str(dest)
            else:
                raise ValueError("Unbekannte Aktion: " + action)
        self.push()
        return True


def main():
    service = DesktopService()
    for line in sys.stdin:
        request = {}
        try:
            parsed = json.loads(line)
            if (
                not isinstance(parsed, dict)
                or not isinstance(parsed.get("action"), str)
                or not isinstance(parsed.get("data") or {}, dict)
            ):
                raise ValueError("Ungültige Anfrage an den Hintergrunddienst.")
            request = parsed
            result = service.command(request["action"], request.get("data") or {})
            service.emit("result", {"id": request.get("id"), "value": result})
            if request["action"] == "shutdown":
                break
        except Exception as exc:
            service.emit("result", {"id": request.get("id"), "error": str(exc)})
    if not service.closed:
        service.command("shutdown", {})


if __name__ == "__main__":
    main()
