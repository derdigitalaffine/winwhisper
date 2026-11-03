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
import sys

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


class FinalizedRecorder:
    # The Windows writer closes the WAV before asking the engine to import it.
    def poll(self):
        return 0


class WindowsService(base.DesktopService):
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
        super().transcribe_work(cancel)

    def command(self, action, data):
        if action == "open_project":
            self.unlocked()
            self.save()
            path = Path(data.get("path", "")).resolve()
            if not path.is_relative_to(core.DATA.resolve()):
                raise ValueError(
                    "Diese Projektdatei liegt außerhalb des Arbeitsbereichs."
                )

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
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or path.suffix != ".wav"
            ):
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
                raise ValueError(
                    "Ollama ist nicht installiert. In der Einrichtung kann es optional für Protokolle und Auswertungen installiert werden."
                )

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
            code = "from faster_whisper.utils import download_model; import sys; print(download_model(sys.argv[1]),flush=True)"
            self.start_job(
                "Whisper-Modell herunterladen",
                lambda cancel: self.run_process(
                    [sys.executable, "-c", code, model], cancel
                ),
            )
            return True
        if action in ("record_start",):
            raise ValueError(
                "Die Aufnahme wird durch die Windows-Oberfläche gestartet."
            )
        if action in ("load_audio", "open_project", "import_transcript"):
            path = Path(data.get("path", "")).resolve()
            if not path.is_relative_to(core.DATA.resolve()):
                raise ValueError(
                    "Diese Datei liegt außerhalb des lokalen Arbeitsbereichs."
                )
        return super().command(action, data)


def serve(service):
    try:
        for line in sys.stdin:
            request = {}
            try:
                parsed = json.loads(line)
                if (
                    not isinstance(parsed, dict)
                    or not isinstance(parsed.get("action"), str)
                    or not isinstance(parsed.get("data") or {}, dict)
                ):
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
