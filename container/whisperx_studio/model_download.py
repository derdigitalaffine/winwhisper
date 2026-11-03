"""Verbose, cache-aware management for local faster-whisper models.

The upstream faster-whisper helper intentionally disables its tqdm progress bar.
For the desktop setup we want the opposite: visible progress, useful diagnostics,
an explicit cache verification and a safe way to remove broken or unused models.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import traceback

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


def cache_dir_for(model: str) -> Path:
    """Return the exact Hugging Face cache directory for one allowlisted model."""
    repo_id = repo_id_for(model)
    return Path(HF_HUB_CACHE) / ("models--" + repo_id.replace("/", "--"))


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
    """Inspect the local cache without touching the network."""
    root = cache_dir_for(model)
    result = {"installed": False, "cached": root.exists(), "size_mb": 0.0}
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


def remove(model: str) -> bool:
    """Remove only the allowlisted model's own Hugging Face repository cache."""
    root = cache_dir_for(model)
    hub = Path(HF_HUB_CACHE).resolve()
    resolved = root.resolve()
    if resolved.parent != hub:
        raise RuntimeError("Whisper-Cachepfad liegt außerhalb des Hugging-Face-Caches.")
    if not root.exists():
        log(f"Whisper {model}: kein lokaler Cache vorhanden.")
        return False
    log(f"Entferne Whisper {model} aus dem lokalen Modell-Cache …")
    shutil.rmtree(root)
    log(f"Whisper {model} wurde lokal entfernt.")
    return True


def download(model: str) -> Path:
    repo_id = repo_id_for(model)

    log(f"Whisper-Download · Modell: {model}")
    log(f"Quelle: https://huggingface.co/{repo_id}")
    log(f"Lokaler Modell-Cache: {HF_HUB_CACHE}")
    log("Prüfe zuerst, ob bereits ein vollständiges lokales Modell vorhanden ist …")

    try:
        cached = snapshot_download(
            repo_id,
            allow_patterns=ALLOW_PATTERNS,
            local_files_only=True,
        )
        root = verify_snapshot(cached)
    except Exception as exc:
        log(f"Noch kein vollständiger lokaler Cache: {type(exc).__name__}: {exc}")
    else:
        size_mb = (root / "model.bin").stat().st_size / (1024 * 1024)
        log(f"Whisper {model} ist bereits lokal vorhanden · model.bin {size_mb:.1f} MB.")
        return root

    log("Starte Download von Hugging Face. Fortschrittsmeldungen folgen direkt darunter.")
    log("Bei Proxy-, Firewall-, Virenscanner- oder Verbindungsproblemen erscheint die genaue Fehlermeldung im Protokoll.")
    downloaded = snapshot_download(repo_id, allow_patterns=ALLOW_PATTERNS)

    log("Download beendet. Prüfe die lokalen Modelldateien …")
    root = verify_snapshot(downloaded)
    cached = snapshot_download(
        repo_id,
        allow_patterns=ALLOW_PATTERNS,
        local_files_only=True,
    )
    verify_snapshot(cached)
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
