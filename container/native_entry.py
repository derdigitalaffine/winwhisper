"""Native Windows stdio entry point for WinWhisper Studio.

WhisperX runs directly in the managed Python environment. Ollama is optional; if
its Windows executable is available, WinWhisper starts a private local server on
127.0.0.1:11435 with models stored inside the WinWhisper workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


def _prepare_ffmpeg():
    """Expose imageio-ffmpeg's verified wheel binary as ffmpeg.exe on PATH."""
    import imageio_ffmpeg

    data = Path(os.environ["WINWHISPER_DATA"])
    bindir = data / "runtime" / "native" / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    target = bindir / "ffmpeg.exe"
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not target.is_file() or target.stat().st_size != source.stat().st_size:
        temporary = target.with_suffix(".tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")


def _ollama_ready(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url.rstrip("/") + "/api/version", timeout=1):
            return True
    except OSError:
        return False


def _start_ollama():
    executable = os.environ.get("WINWHISPER_OLLAMA", "").strip()
    if not executable or not Path(executable).is_file():
        print(
            "Ollama ist nicht installiert; Transkription funktioniert trotzdem. "
            "Auswertungen bleiben optional.",
            file=sys.stderr,
            flush=True,
        )
        return None, None

    url = os.environ.get("WINWHISPER_OLLAMA_URL", "http://127.0.0.1:11435")
    if _ollama_ready(url):
        return None, None

    data = Path(os.environ["WINWHISPER_DATA"])
    log_path = data / "logs" / "ollama-native.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [executable, "serve"],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        env=os.environ.copy(),
        creationflags=flags,
    )
    for _ in range(100):
        if process.poll() is not None:
            print(
                "Ollama konnte nicht gestartet werden; Transkription bleibt verfügbar. "
                "Siehe logs/ollama-native.log.",
                file=sys.stderr,
                flush=True,
            )
            log.close()
            return None, None
        if _ollama_ready(url):
            print("Lokales Ollama für WinWhisper gestartet.", file=sys.stderr, flush=True)
            return process, log
        time.sleep(0.2)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    log.close()
    print(
        "Ollama antwortete nicht rechtzeitig; Transkription bleibt verfügbar.",
        file=sys.stderr,
        flush=True,
    )
    return None, None


def main():
    # WhisperX 3.8.6 decodes diarization input with its own load_audio helper and
    # passes pyannote an in-memory waveform. TorchCodec's optional file decoder
    # therefore must not become a native-startup dependency on Windows.
    _prepare_ffmpeg()
    ollama, log = _start_ollama()
    service = None
    try:
        from whisperx_studio.managed_windows_service import WindowsService, serve

        service = WindowsService()
        serve(service)
    finally:
        if service is not None and not service.closed:
            try:
                service.command("shutdown", {})
            except Exception:
                pass
        if ollama is not None and ollama.poll() is None:
            ollama.terminate()
            try:
                ollama.wait(timeout=5)
            except subprocess.TimeoutExpired:
                ollama.kill()
                ollama.wait()
        if log is not None:
            log.close()


if __name__ == "__main__":
    main()
