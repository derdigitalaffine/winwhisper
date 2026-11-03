"""Whisper model management layered on top of the Windows desktop service."""

from __future__ import annotations

import threading

from .model_download import MODELS, model_statuses, remove as remove_model
from .windows_service import WindowsService as BaseWindowsService, serve


class WindowsService(BaseWindowsService):
    """Expose installed Whisper models and safe cache removal to the desktop UI."""

    def _state(self):
        state = super()._state()
        try:
            state["whisper_models"] = model_statuses()
        except Exception as exc:
            self.log("Whisper-Modellstatus konnte nicht gelesen werden: " + str(exc))
            state["whisper_models"] = {
                model: {"installed": False, "cached": False, "size_mb": 0.0}
                for model in MODELS
            }
        return state

    def command(self, action, data):
        if action == "remove_asr":
            model = str((data or {}).get("model", ""))
            if model not in MODELS:
                raise ValueError("Ungültiges Whisper-Modell.")

            def remove_work(cancel: threading.Event):
                if cancel.is_set():
                    raise InterruptedError()
                self.status = f"Whisper {model} wird lokal entfernt …"
                self.push()
                self.log(f"Whisper-Modell entfernen: {model}")
                removed = remove_model(model)
                if cancel.is_set():
                    raise InterruptedError()
                self.status = (
                    f"Whisper {model} wurde lokal entfernt."
                    if removed
                    else f"Whisper {model} war nicht lokal installiert."
                )
                self.log(self.status)
                self.push()

            self.start_job("Whisper-Modell entfernen", remove_work)
            return True
        return super().command(action, data)


__all__ = ["WindowsService", "serve"]
