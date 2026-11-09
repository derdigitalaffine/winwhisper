"""Adapt the project/analysis engine to Windows-hosted PCM recording.

The service is shared by the Docker runtime and the native Windows runtime. Paths,
Ollama and the WhisperX launcher are selected through environment variables when
running natively; Docker keeps its existing defaults.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from . import core

core.DATA = Path(os.environ.get("WINWHISPER_DATA", "/data"))
from . import desktop_service as base

base.DATA = core.DATA
base.PYTHON = Path(sys.executable)
base.ROOT = Path(os.environ.get("WINWHISPER_ENGINE", str(Path(__file__).resolve().parents[1])))
base.CLI = Path(os.environ.get("WINWHISPER_CLI", "/app/whisperx-cli"))
from . import analysis

analysis.OLLAMA = os.environ.get("WINWHISPER_OLLAMA_URL", analysis.OLLAMA)
OllamaClient = analysis.OllamaClient


def find_ollama():
    configured = os.environ.get("WINWHISPER_OLLAMA", "").strip()
    if configured and Path(configured).is_file():
        return configured
    command = shutil.which("ollama")
    if command:
        return command
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        for candidate in (
            local / "Programs" / "Ollama" / "ollama.exe",
            local / "Ollama" / "ollama.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def workspace_path(value):
    """Resolve the desktop's portable /data path into the active workspace.

    The Electron file boundary deliberately keeps using /data/... logical paths so
    the same renderer and export code works with Docker and native Windows. Native
    Python receives those logical paths and maps them to its real Windows workspace.
    Direct host paths are accepted only when they are already inside that workspace.
    """
    root = core.DATA.resolve()
    text = str(value or "")
    if text.startswith("/data/"):
        parts = text[6:].split("/")
        if not parts or any(not part or part in (".", "..") or ":" in part or "\\" in part for part in parts):
            raise ValueError("Ungültiger Arbeitsbereichspfad.")
        resolved = root.joinpath(*parts).resolve()
    else:
        resolved = Path(text).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Diese Datei liegt außerhalb des lokalen Arbeitsbereichs.")
    return resolved


class FinalizedRecorder:
    # The Windows writer closes the WAV before asking the engine to import it.
    def poll(self):
        return 0


class WindowsService(base.DesktopService):
    PATH_ACTIONS = {
        "external_record_start",
        "load_audio",
        "open_project",
        "import_transcript",
        "save_as",
        "export_audio",
        "export_report",
        "export_transcript",
    }

    @staticmethod
    def cli_command(*args):
        if base.CLI.suffix.lower() == ".py":
            return [sys.executable, str(base.CLI), *args]
        return [str(base.CLI), *args]

    @staticmethod
    def stop_process(proc):
        if not proc or proc.poll() is not None:
            return
        if os.name == "nt":
            # Kill the complete worker tree. WhisperX may have spawned model
            # workers; leaving those alive keeps VRAM and file handles locked.
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                check=False,
            )
            return
        return base.DesktopService.stop_process(proc)

    def run_process(self, command, cancel, on_line=None, secret=None):
        if os.name != "nt":
            return super().run_process(command, cancel, on_line, secret)
        if cancel.is_set() or self.closed:
            raise InterruptedError()
        proc = subprocess.Popen(
            command,
            cwd=str(base.ROOT),
            stdin=subprocess.PIPE if secret is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            creationflags=(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        self.proc = proc
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
            if proc.poll() is None:
                self.stop_process(proc)
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.stop_process(proc)
                    proc.wait()
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if self.proc is proc:
                self.proc = None
        if cancel.is_set():
            raise InterruptedError()
        if code:
            raise RuntimeError(
                f"Verarbeitung fehlgeschlagen (Exit-Code {code}). Details im Aktivitätsprotokoll."
            )

    def validate_project_paths(self, project):
        root = core.DATA.resolve()
        for name in ("source", "preview", "directory"):
            if not Path(project[name]).resolve().is_relative_to(root):
                raise ValueError(
                    "Das Projekt verweist auf Dateien außerhalb des Windows-Arbeitsbereichs. Bitte Audio und Transkript neu importieren."
                )
        if any(
            not Path(p).resolve().is_relative_to(root) for p in project.get("undo", [])
        ):
            raise ValueError(
                "Der Schnittverlauf verweist auf Dateien außerhalb des Arbeitsbereichs."
            )

    def _state(self):
        state = super()._state()
        state["platform"] = os.environ.get("WINWHISPER_PLATFORM", "windows-container")
        return state

    def _refresh_connections(self):
        try:
            self.models = OllamaClient().models()
            self.model_status = "Gemma / Qwen · vollständig lokal"
        except Exception as exc:
            self.models = []
            self.model_status = "Ollama optional · nicht erreichbar"
            self.log(str(exc))
        self.push()

    def validate_settings(self, values, available_microphone=True):
        if not isinstance(values, dict):
            raise ValueError("Ungültige Einstellungen.")
        microphone = values.get("microphone", "")
        if not isinstance(microphone, str) or len(microphone) > 512:
            raise ValueError("Ungültiges Mikrofon.")
        super().validate_settings(
            {k: v for k, v in values.items() if k != "microphone"}, False
        )

    def start_live(self, path):
        out = Path.home() / "Dokumente/Transkripte" / (path.stem + "_live")
        out.mkdir(parents=True, exist_ok=True)
        self.live_stop = out / "stop.signal"
        self.live_stop.unlink(missing_ok=True)
        command = self.cli_command(
            "--live", "--audio", str(path), "--output", str(out),
            "--stop-file", str(self.live_stop), "--language", self.settings["language"],
            "--device", self.settings["device"]
        )
        kwargs = {
            "cwd": str(base.ROOT),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "errors": "replace",
        }
        if os.name == "nt":
            kwargs["creationflags"] = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            kwargs["start_new_session"] = True
        self.live_proc = subprocess.Popen(command, **kwargs)
        live_proc = self.live_proc

        def live_reader():
            for line in live_proc.stdout:
                try:
                    event = json.loads(line)
                    if event.get("type") == "partial":
                        self.live_segments.append(
                            {k: event[k] for k in ("start", "end", "text", "words") if k in event}
                        )
                        self.emit("live", event)
                    elif event.get("type") in ("error", "diagnostic", "ready"):
                        self.log(event.get("message", "Live-Fehler"))
                except (ValueError, TypeError, AttributeError):
                    self.log(line)

        self.live_reader_thread = threading.Thread(target=live_reader, daemon=True)
        self.live_reader_thread.start()

    def transcribe_work(self, cancel):
        # Free LLM VRAM before loading WhisperX when Ollama is available. Native
        # transcription must remain usable when Ollama was deliberately skipped.
        try:
            client = OllamaClient()
            for model in client.request("/api/ps").get("models", []):
                if cancel.is_set():
                    raise InterruptedError()
                client.unload(model["name"])
        except InterruptedError:
            raise
        except Exception as exc:
            self.log("Ollama ist nicht aktiv; Transkription läuft ohne Auswertungsmodell. " + str(exc))

        self.require_project()
        settings = dict(self.settings)
        self.status = "Audiofassung vorbereiten …"
        self.push()
        working = self.doc.render(Path(self.project["directory"]) / "working.wav", cancel=cancel)
        out = Path.home() / "Dokumente/Transkripte" / (
            "Studio_" + base.dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + base.uuid.uuid4().hex[:5]
        )
        cmd = self.cli_command(
            str(working), "--model", settings["asr_model"], "--studio-performance", "--vad_method", "silero", "--output_dir", str(out)
        )
        if settings["device"] == "auto":
            cmd.append("--studio-auto-device")
        else:
            cmd += ["--device", "cuda" if settings["device"] == "gpu" else "cpu"]
        if settings["language"] != "auto":
            cmd += ["--language", settings["language"]]
        if settings["diarize"]:
            cmd += ["--diarize", "--max_speakers", "15" if settings["speaker_count"] == "auto" else str(settings["speaker_count"])]
            if settings["speaker_count"] != "auto":
                cmd += ["--min_speakers", str(settings["speaker_count"])]
        self.status = "WhisperX transkribiert die Aufnahme …"
        self.push()
        self.run_process(cmd, cancel)
        files = sorted(out.glob("*.json"))
        if not files:
            raise ValueError("WhisperX hat kein JSON-Transkript erzeugt.")
        candidate = base.copy.deepcopy(self.project)
        candidate["segments"] = base.transcript_segments(json.loads(files[0].read_text(encoding="utf-8")))
        candidate.pop("preliminary", None)
        if cancel.is_set():
            raise InterruptedError()
        self.commit_project(candidate)
        self.status = f"Transkript fertig · {len(self.project['segments'])} Abschnitte."

    def command(self, action, data):
        if action in self.PATH_ACTIONS and isinstance(data, dict) and "path" in data:
            data = dict(data)
            data["path"] = str(workspace_path(data["path"]))
        if action == "open_project":
            self.unlocked()
            self.save()
            path = Path(data.get("path", "")).resolve()
            if not path.is_relative_to(core.DATA.resolve()):
                raise ValueError("Diese Projektdatei liegt außerhalb des Arbeitsbereichs.")

            def load(cancel):
                project = core.load_project(path)
                self.validate_project_paths(project)
                self.ensure_preview(project, cancel)
                peaks = core.read_peaks(project["preview"], cancel)
                if cancel.is_set():
                    raise InterruptedError()
                self.activate(project, peaks, path)

            self.status = "Windows-Projekt wird geöffnet …"
            self.start_job("Projekt öffnen", load)
            return True
        if action == "undo" and self.project and self.project.get("undo"):
            self.validate_project_paths(core.load_project(self.project["undo"][-1]))
        if action == "external_record_start":
            self.unlocked()
            self.save()
            path = Path(data["path"]).resolve()
            root = (core.DATA / "recordings").resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.suffix != ".wav":
                raise ValueError("Ungültige lokale Aufnahmedatei.")
            self.record_proc = FinalizedRecorder()
            self.record_path, self.record_log = path, None
            self.project = self.doc = self.project_path = None
            self.live_segments = []
            self.status = "Windows-Mikrofonaufnahme läuft …"
            if self.settings["live"]:
                try:
                    self.start_live(path)
                except OSError as exc:
                    self.log("Live-Start fehlgeschlagen: " + str(exc))
            self.push()
            return True
        if action == "model_pull":
            model = data.get("model", "")
            if model not in ("gemma4:e2b", "qwen3:14b-q4_K_M"):
                raise ValueError("Bitte Gemma oder Qwen aus der Modellauswahl wählen.")
            executable = find_ollama()
            if not executable:
                raise ValueError("Ollama ist nicht installiert. In der Einrichtung kann es optional für Protokolle und Auswertungen installiert werden.")

            def download(cancel):
                self.status = "Modell wird lokal heruntergeladen: " + model
                self.push()
                self.run_process([executable, "pull", model], cancel)
                self._refresh_connections()
                self.status = "Modell lokal bereit: " + model

            self.start_job("Modell herunterladen", download)
            return True
        if action == "warmup_asr":
            model = data.get("model", "small")
            if model not in ("tiny", "base", "small", "medium", "large-v3"):
                raise ValueError("Ungültiges Whisper-Modell.")

            def download_asr(cancel):
                self.status = f"Whisper {model} wird heruntergeladen und geprüft …"
                self.push()
                self.log(f"Whisper-Modell angefordert: {model}. Der Download wird ausführlich protokolliert.")
                self.run_process(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "whisperx_studio.model_download",
                        model,
                    ],
                    cancel,
                )
                self.status = f"Whisper {model} ist lokal bereit."
                self.log(self.status)
                self.push()

            self.start_job("Whisper-Modell herunterladen", download_asr)
            return True
        if action == "setup_speakers" and base.CLI.suffix.lower() == ".py":
            secret = str(data.get("token", "")).strip()
            if not secret.startswith("hf_"):
                raise ValueError("Bitte einen gültigen Hugging-Face-Read-Token eingeben.")
            code = "import runpy,sys; from huggingface_hub import login; login(token=sys.stdin.read().strip(),add_to_git_credential=False); script=sys.argv[1]; sys.argv=[script,'--setup-speakers']; runpy.run_path(script,run_name='__main__')"
            self.status = "Sprechermodell wird eingerichtet …"
            self.start_job("Sprecher einrichten", lambda cancel: self.run_process([sys.executable, "-c", code, str(base.CLI)], cancel, secret=secret))
            return True
        if action in ("record_start",):
            raise ValueError("Die Aufnahme wird durch die Windows-Oberfläche gestartet.")
        if action in ("load_audio", "open_project", "import_transcript"):
            path = Path(data.get("path", "")).resolve()
            if not path.is_relative_to(core.DATA.resolve()):
                raise ValueError("Diese Datei liegt außerhalb des lokalen Arbeitsbereichs.")
        return super().command(action, data)


def serve(service):
    try:
        for line in sys.stdin:
            request = {}
            try:
                parsed = json.loads(line)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("action"), str) or not isinstance(parsed.get("data") or {}, dict):
                    raise ValueError("Ungültige Desktop-Anfrage.")
                request = parsed
                value = service.command(request["action"], request.get("data") or {})
                service.emit("result", {"id": request.get("id"), "value": value})
                if request["action"] == "shutdown":
                    break
            except Exception as exc:
                service.emit("result", {"id": request.get("id"), "error": str(exc)})
    finally:
        if not service.closed:
            service.command("shutdown", {})
