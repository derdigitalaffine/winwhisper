"""Verbose, cache-aware management for local faster-whisper models.

The upstream faster-whisper helper intentionally disables its tqdm progress bar.
For the desktop setup we want the opposite: visible progress, useful diagnostics,
an explicit cache verification and a safe way to remove broken or unused models.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import sys
import traceback

# WhisperX 3.8.6 currently resolves huggingface-hub 0.x. On Windows that client
# automatically falls back to copying files when symlinks are unavailable, but a
# cache previously written by Docker/WSL can still contain Linux-style symlinks.
# The desktop runtime therefore gives native Windows its own HF_HOME. Keep Xet
# disabled for this helper and silence only the expected Windows symlink warning.
if os.name == "nt":
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HF_HUB_CACHE


MODELS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]
REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json")


def log(message: str) -> None:
    print(message, flush=True)


def repo_id_for(model: str) -> str:
    repo_id = MODELS.get(model)
    if not repo_id:
        raise ValueError(
            "Ungültiges Whisper-Modell. Erlaubt: " + ", ".join(MODELS)
        )
    return repo_id


def _repo_cache(root: Path, model: str) -> Path:
    repo_id = repo_id_for(model)
    return root / ("models--" + repo_id.replace("/", "--"))


def cache_dir_for(model: str) -> Path:
    """Return the active Hugging Face repository cache for one allowlisted model."""
    return _repo_cache(Path(HF_HUB_CACHE), model)


def legacy_cache_dir_for(model: str) -> Path | None:
    """Return the old shared Docker/native cache path when a workspace is known."""
    data = os.environ.get("WINWHISPER_DATA", "").strip()
    if not data:
        return None
    legacy_hub = Path(data) / "models" / "huggingface" / "hub"
    legacy = _repo_cache(legacy_hub, model)
    try:
        if legacy.resolve() == cache_dir_for(model).resolve():
            return None
    except OSError:
        pass
    return legacy


def verify_snapshot(path: str | Path) -> Path:
    root = Path(path)
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise RuntimeError(
            "Whisper-Cache ist unvollständig; es fehlen: " + ", ".join(missing)
        )
    model_file = root / "model.bin"
    if model_file.stat().st_size < 1024 * 1024:
        raise RuntimeError("Whisper model.bin ist unerwartet klein und vermutlich unvollständig.")
    return root


def model_status(model: str) -> dict:
    """Inspect the active cache; legacy cache presence enables cleanup in setup."""
    root = cache_dir_for(model)
    legacy = legacy_cache_dir_for(model)
    legacy_present = bool(legacy and legacy.exists())
    result = {
        "installed": False,
        "cached": root.exists() or legacy_present,
        "legacy": legacy_present,
        "size_mb": 0.0,
    }
    snapshots = root / "snapshots"
    if not snapshots.is_dir():
        return result
    try:
        candidates = sorted(
            (entry for entry in snapshots.iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return result
    for candidate in candidates:
        try:
            verified = verify_snapshot(candidate)
        except (OSError, RuntimeError):
            continue
        result["installed"] = True
        result["cached"] = True
        result["size_mb"] = round(
            (verified / "model.bin").stat().st_size / (1024 * 1024), 1
        )
        break
    return result


def model_statuses() -> dict:
    return {model: model_status(model) for model in MODELS}


def _make_writable(root: Path) -> None:
    """Best-effort removal of Windows read-only flags from a disposable cache."""
    try:
        entries = [root, *root.rglob("*")]
    except OSError:
        entries = [root]
    for entry in entries:
        try:
            os.chmod(entry, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


def _retry_remove_readonly(function, path, _excinfo) -> None:
    """shutil.rmtree callback for read-only files left by old Windows caches."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    function(path)


def _remove_cache_root(root: Path) -> bool:
    if not root.exists():
        return False
    _make_writable(root)
    shutil.rmtree(root, onexc=_retry_remove_readonly)
    if root.exists():
        raise PermissionError(f"Cache konnte nicht vollständig entfernt werden: {root}")
    return True


def remove(model: str) -> bool:
    """Remove only allowlisted model caches from active and legacy HF locations."""
    repo_id_for(model)
    roots = [cache_dir_for(model)]
    legacy = legacy_cache_dir_for(model)
    if legacy is not None:
        roots.append(legacy)

    removed = False
    for root in roots:
        log(f"Prüfe Whisper-{model}-Cache: {root}")
        if _remove_cache_root(root):
            removed = True
            log(f"Whisper {model}: Cache entfernt: {root}")
    if not removed:
        log(f"Whisper {model}: kein lokaler Cache vorhanden.")
        return False
    log(f"Whisper {model} wurde lokal entfernt.")
    return True


def _permission_message(model: str, exc: PermissionError) -> RuntimeError:
    path = getattr(exc, "filename", None) or str(exc)
    return RuntimeError(
        "Windows verweigert den Zugriff auf eine Datei im Whisper-Cache "
        f"({path}). Das kann bei einem älteren oder abgebrochenen Cache aus "
        "Docker/WSL auftreten. In der Einrichtung das ausgewählte Whisper-Modell "
        "entfernen und danach erneut installieren; WinWhisper verwendet nativ "
        "einen getrennten Windows-Cache."
    )


def download(model: str) -> Path:
    repo_id = repo_id_for(model)

    log(f"Whisper-Download · Modell: {model}")
    log(f"Quelle: https://huggingface.co/{repo_id}")
    log(f"Lokaler Modell-Cache: {HF_HUB_CACHE}")
    if os.name == "nt":
        log("Windows-Modus: eigener nativer Hugging-Face-Cache; keine Docker/WSL-Symlinks werden wiederverwendet.")
    legacy = legacy_cache_dir_for(model)
    if legacy and legacy.exists():
        log(f"Alter gemeinsamer Cache erkannt: {legacy}. Er wird nicht für die native Installation verwendet und kann über „entfernen“ gelöscht werden.")
    log("Prüfe zuerst, ob bereits ein vollständiges lokales Modell vorhanden ist …")

    try:
        cached = snapshot_download(
            repo_id,
            allow_patterns=ALLOW_PATTERNS,
            local_files_only=True,
        )
        root = verify_snapshot(cached)
    except PermissionError as exc:
        raise _permission_message(model, exc) from exc
    except Exception as exc:
        log(f"Noch kein vollständiger lokaler Cache: {type(exc).__name__}: {exc}")
    else:
        size_mb = (root / "model.bin").stat().st_size / (1024 * 1024)
        log(f"Whisper {model} ist bereits lokal vorhanden · model.bin {size_mb:.1f} MB.")
        return root

    log("Starte Download von Hugging Face. Fortschrittsmeldungen folgen direkt darunter.")
    log("Bei Proxy-, Firewall-, Virenscanner- oder Verbindungsproblemen erscheint die genaue Fehlermeldung im Protokoll.")
    try:
        downloaded = snapshot_download(repo_id, allow_patterns=ALLOW_PATTERNS)
    except PermissionError as exc:
        raise _permission_message(model, exc) from exc

    log("Download beendet. Prüfe die lokalen Modelldateien …")
    root = verify_snapshot(downloaded)
    try:
        cached = snapshot_download(
            repo_id,
            allow_patterns=ALLOW_PATTERNS,
            local_files_only=True,
        )
        verify_snapshot(cached)
    except PermissionError as exc:
        raise _permission_message(model, exc) from exc
    size_mb = (root / "model.bin").stat().st_size / (1024 * 1024)
    log(f"Whisper {model} lokal verifiziert · model.bin {size_mb:.1f} MB.")
    log(f"Bereit: {root}")
    return root


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 1 and args[0] == "--status":
            log(json.dumps(model_statuses(), ensure_ascii=False))
            return 0
        if len(args) == 2 and args[0] == "--remove":
            remove(args[1])
            return 0
        if len(args) == 1:
            download(args[0])
            return 0
        log("Aufruf: python -m whisperx_studio.model_download <tiny|base|small|medium|large-v3> | --remove <modell> | --status")
        return 2
    except Exception as exc:
        log(f"Whisper-Modellverwaltung fehlgeschlagen · {type(exc).__name__}: {exc}")
        log("Diagnose: Internetverbindung, Proxy/Firewall/Virenscanner und freien Speicherplatz prüfen; bei einem beschädigten Cache das Modell in der Einrichtung entfernen und erneut laden.")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
