"""Container/native entry for batch transcription, live text and speaker setup."""

import os
from pathlib import Path
import runpy
import sys

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")
if "--live" in sys.argv:
    sys.argv.remove("--live")
    runpy.run_path(
        str(Path(__file__).with_name("whisperx_live.py")), run_name="__main__"
    )
    raise SystemExit(0)
if "--studio-auto-device" in sys.argv:
    import ctranslate2
    import torch

    sys.argv.remove("--studio-auto-device")
    cuda = torch.cuda.is_available() and ctranslate2.get_cuda_device_count() > 0
    sys.argv += ["--device", "cuda" if cuda else "cpu"]
if "--setup-speakers" in sys.argv:
    import torch
    from huggingface_hub import get_token
    from whisperx.diarize import DiarizationPipeline

    if not get_token():
        raise SystemExit(
            "Bitte zuerst den Hugging-Face-Read-Token in der App hinterlegen."
        )
    DiarizationPipeline(device="cuda" if torch.cuda.is_available() else "cpu")
    print("Sprechermodell lokal bereit.", flush=True)
else:
    from whisperx.__main__ import cli

    cli()
