"""Verbose, cache-aware downloader for local faster-whisper models.

The upstream faster-whisper helper intentionally disables its tqdm progress bar.
For the desktop setup we want the opposite: visible progress, useful diagnostics and
an explicit cache verification before reporting success.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback

from huggingface_hub import snapshot_download


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


def download(model: str) -> Path:
    repo_id = MODELS.get(model)
    if not repo_id:
        raise ValueError(
            "Ungültiges Whisper-Modell. Erlaubt: " + ", ".join(MODELS)
        )

    cache_root = os.environ.get("HF_HOME") or "Hugging-Face-Standardcache"
    log(f"Whisper-Download · Modell: {model}")
    log(f"Quelle: https://huggingface.co/{repo_id}")
    log(f"Lokaler Modell-Cache: {cache_root}")
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
    # A second local-only lookup ensures the snapshot is actually resolvable from
    # the cache that WhisperX/faster-whisper will use later, without network access.
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
    if len(args) != 1:
        log("Aufruf: python -m whisperx_studio.model_download <tiny|base|small|medium|large-v3>")
        return 2
    try:
        download(args[0])
        return 0
    except Exception as exc:
        log(f"Whisper-Download fehlgeschlagen · {type(exc).__name__}: {exc}")
        log("Diagnose: Internetverbindung, Proxy/Firewall/Virenscanner und freien Speicherplatz prüfen; danach kann der Download erneut gestartet werden.")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
