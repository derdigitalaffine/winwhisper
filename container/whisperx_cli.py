"""Container/native entry with isolated GPU retries and observable CPU fallback."""
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback

from whisperx_studio.gpu_runtime import gpu_failure, policy, prepare_cuda


def option(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def replace(args, name, value):
    if name in args:
        index = args.index(name)
        del args[index:index + 2]
    args.extend([name, str(value)])


def main():
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")
    prepare_cuda()
    if os.name == "nt" and os.environ.get("WINWHISPER_DATA"):
        from native_entry import _prepare_ffmpeg
        _prepare_ffmpeg()
    if "--live" in sys.argv:
        sys.argv.remove("--live")
        runpy.run_path(str(Path(__file__).with_name("whisperx_live.py")), run_name="__main__")
        return
    if "--setup-speakers" in sys.argv:
        from huggingface_hub import get_token
        from whisperx.diarize import DiarizationPipeline
        if not get_token():
            raise SystemExit("Bitte zuerst den Hugging-Face-Read-Token in der App hinterlegen.")
        selected = policy()
        DiarizationPipeline(device=selected["device"])
        print("Sprechermodell lokal bereit.", flush=True)
        return
    # Leave upstream help and explicitly configured external CLI calls intact.
    if "--studio-auto-device" not in sys.argv and "--studio-performance" not in sys.argv:
        from whisperx.__main__ import cli
        cli()
        return
    args = sys.argv[1:]
    requested = "auto" if "--studio-auto-device" in args else option(args, "--device", "cpu")
    args = [arg for arg in args if arg not in ("--studio-auto-device", "--studio-performance")]
    if os.environ.get("WINWHISPER_GPU_WORKER") == "1":
        selected = policy("cpu" if os.environ.get("WINWHISPER_CPU_RETRY") == "1" else requested,
                          batch_limit=int(os.environ.get("WINWHISPER_BATCH_LIMIT", "16")),
                          compact=os.environ.get("WINWHISPER_COMPACT") == "1")
        for name, value in (("--device", selected["device"]), ("--compute_type", selected["compute"]), ("--batch_size", selected["batch"])):
            replace(args, name, value)
        print(f"WinWhisper: {selected['device']} · {selected['compute']} · Batch {selected['batch']} · {selected['reason']}", file=sys.stderr, flush=True)
        sys.argv = [sys.argv[0], *args]
        try:
            from whisperx.__main__ import cli
            cli()
        except Exception as exc:
            kind = gpu_failure(exc) if selected["device"] == "cuda" else None
            traceback.print_exc()
            raise SystemExit(75 if kind == "oom" else 76 if kind == "cuda" else 1)
        return
    # A fresh process for each attempt releases *all* torch/CT2 allocations.
    # Only CUDA faults are retried; downloads/auth/audio errors remain errors.
    env = os.environ.copy()
    env["WINWHISPER_GPU_WORKER"] = "1"
    env.pop("WINWHISPER_CPU_RETRY", None)
    env.pop("WINWHISPER_COMPACT", None)
    env.pop("WINWHISPER_BATCH_LIMIT", None)
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    while True:
        code = subprocess.call(command, env=env, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        if code == 75 and env.get("WINWHISPER_COMPACT") != "1":
            print("WinWhisper: GPU-Speicher knapp; erneuter Versuch mit kompakter Präzision und Batch 1.", file=sys.stderr, flush=True)
            env.update(WINWHISPER_COMPACT="1", WINWHISPER_BATCH_LIMIT="1")
        elif code in (75, 76) and requested == "auto" and env.get("WINWHISPER_CPU_RETRY") != "1":
            print("WinWhisper: CUDA-Laufzeitfehler; CPU-Fallback (int8). Details stehen oben im Protokoll.", file=sys.stderr, flush=True)
            env["WINWHISPER_CPU_RETRY"] = "1"
        else:
            raise SystemExit(code)


if __name__ == "__main__":
    main()
