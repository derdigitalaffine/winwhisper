"""Native Windows stdio entry point for WinWhisper Studio.

WhisperX runs directly in the managed Python environment. Ollama is optional; if
its Windows executable is available, WinWhisper starts a private local server on
127.0.0.1:11435 with models stored inside the WinWhisper workspace.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

TORCHCODEC_FFMPEG_URL = (
    "https://pytorch.s3.amazonaws.com/torchcodec/ffmpeg/2025-03-14/"
    "windows_x86_64/7.0.1.tar.gz"
)
TORCHCODEC_FFMPEG_SHA256 = (
    "ae391ace382330e912793b70b68529ee7c91026d2869b4df7e7c3e7d3656bdd5"
)
_DLL_HANDLES = []


def _find_ffmpeg_dll_dir(root: Path):
    for dll in root.rglob("avcodec*.dll"):
        directory = dll.parent
        if any(directory.glob("avformat*.dll")) and any(directory.glob("avutil*.dll")):
            return directory
    return None


def _download_torchcodec_ffmpeg(target: Path):
    """Install TorchCodec's own pinned Windows FFmpeg 7 runtime locally."""
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.parent / "ffmpeg-7.0.1-windows-x86_64.tar.gz.part"
    staging = target.parent / (target.name + ".part")
    shutil.rmtree(staging, ignore_errors=True)
    archive.unlink(missing_ok=True)
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(TORCHCODEC_FFMPEG_URL, timeout=120) as response, archive.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest().lower() != TORCHCODEC_FFMPEG_SHA256:
            raise RuntimeError("FFmpeg-Download hat eine unerwartete SHA-256-Prüfsumme.")
        staging.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            root = staging.resolve()
            for member in members:
                if member.issym() or member.islnk():
                    raise RuntimeError("FFmpeg-Archiv enthält unerwartete Verknüpfungen.")
                destination = (staging / member.name).resolve()
                if not destination.is_relative_to(root):
                    raise RuntimeError("FFmpeg-Archiv enthält einen ungültigen Pfad.")
            bundle.extractall(staging, members=members)
        if not _find_ffmpeg_dll_dir(staging):
            raise RuntimeError("FFmpeg-Archiv enthält keine erwarteten Shared Libraries.")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def _prepare_torchcodec_dlls(strict=False):
    """Expose a verified FFmpeg 7 shared runtime to TorchCodec on Windows.

    TorchCodec 0.7 is paired with PyTorch 2.8 and supports FFmpeg 4-7. Its own
    project publishes a Windows FFmpeg 7.0.1 bundle with a fixed SHA-256. Keeping
    that runtime inside the WinWhisper workspace avoids system-wide FFmpeg,
    administrator rights, WSL and Docker.
    """
    if os.name != "nt":
        return None
    data = Path(os.environ["WINWHISPER_DATA"])
    target = data / "runtime" / "native" / "ffmpeg-shared-7.0.1"
    dll_dir = _find_ffmpeg_dll_dir(target) if target.is_dir() else None
    if dll_dir is None:
        try:
            print("FFmpeg-Shared-Laufzeit für Sprechertrennung wird eingerichtet …", file=sys.stderr, flush=True)
            _download_torchcodec_ffmpeg(target)
            dll_dir = _find_ffmpeg_dll_dir(target)
        except Exception as exc:
            if strict:
                raise RuntimeError("FFmpeg-Shared-Laufzeit für TorchCodec konnte nicht eingerichtet werden: " + str(exc)) from exc
            print(
                "Hinweis: Sprechertrennung ist derzeit nicht bereit, Transkription funktioniert weiter. " + str(exc),
                file=sys.stderr,
                flush=True,
            )
            return None
    if dll_dir is None:
        if strict:
            raise RuntimeError("FFmpeg-Shared-Laufzeit für TorchCodec wurde nicht gefunden.")
        return None
    os.environ["WINWHISPER_FFMPEG_SHARED"] = str(dll_dir)
    os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        _DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))
    return dll_dir


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
        print("Ollama ist nicht installiert; Transkription funktioniert trotzdem. Auswertungen bleiben optional.", file=sys.stderr, flush=True)
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
            print("Ollama konnte nicht gestartet werden; Transkription bleibt verfügbar. Siehe logs/ollama-native.log.", file=sys.stderr, flush=True)
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
    print("Ollama antwortete nicht rechtzeitig; Transkription bleibt verfügbar.", file=sys.stderr, flush=True)
    return None, None


def main():
    _prepare_torchcodec_dlls()
    _prepare_ffmpeg()
    ollama, log = _start_ollama()
    service = None
    try:
        from whisperx_studio.windows_service import WindowsService, serve

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
