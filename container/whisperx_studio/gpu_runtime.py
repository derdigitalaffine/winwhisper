"""Shared CUDA bootstrap and execution policy for setup, diagnostics and workers.

Keep this module importable without torch/CT2 installed. Windows' DLL directory
handles must stay alive for the lifetime of the process (Python 3.8+).
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import sys

_DLL_HANDLES = []
_DLL_PATHS = []


def prepare_cuda():
    if os.name != "nt" or _DLL_PATHS:
        return list(_DLL_PATHS)
    site = Path(sys.prefix) / "Lib" / "site-packages"
    candidates = [site / "torch" / "lib"]
    candidates += sorted((site / "nvidia").glob("*/bin"))
    for directory in candidates:
        if directory.is_dir():
            _DLL_PATHS.append(str(directory))
            _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
    # CT2 loads CUDA libraries dynamically; PATH is needed in addition to the
    # CPython extension loader's AddDllDirectory search path.
    os.environ["PATH"] = os.pathsep.join(_DLL_PATHS + [os.environ.get("PATH", "")])
    return list(_DLL_PATHS)


def probe():
    paths = prepare_cuda()
    result = dict(torchCuda=False, torchVersion="", cudaVersion=None,
                  ct2Devices=0, computeTypes=[], ct2Error="", ready=False,
                  dllPaths=paths, freeMb=0, deviceName="")
    try:
        import torch
        result.update(torchVersion=str(torch.__version__), cudaVersion=torch.version.cuda)
        if not torch.cuda.is_available():
            raise RuntimeError("PyTorch ist ohne nutzbares CUDA installiert; GPU-Einrichtung/Treiber prüfen.")
        # Device count alone does not detect unsupported architectures/drivers.
        value = torch.ones(1, device="cuda") + 1
        torch.cuda.synchronize()
        del value
        result.update(torchCuda=True, deviceName=torch.cuda.get_device_name(0),
                      freeMb=int(torch.cuda.mem_get_info(0)[0] / 1048576))
        # Preload the exact wheel-provided DLLs, never a random system toolkit.
        if os.name == "nt":
            for name in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll"):
                location = next((Path(p) / name for p in paths if (Path(p) / name).is_file()), None)
                if location is None:
                    raise RuntimeError(f"CUDA-DLL fehlt in der Python-Umgebung: {name}")
                _DLL_HANDLES.append(ctypes.WinDLL(str(location)))
        import ctranslate2
        result["ct2Devices"] = int(ctranslate2.get_cuda_device_count())
        if result["ct2Devices"] < 1:
            raise RuntimeError("CTranslate2 erkennt keine CUDA-GPU.")
        result["computeTypes"] = sorted(ctranslate2.get_supported_compute_types("cuda", 0))
        result["ready"] = bool(result["computeTypes"])
        if not result["ready"]:
            raise RuntimeError("CTranslate2 meldet keine unterstützte CUDA-Rechenpräzision.")
    except Exception as exc:
        result["ct2Error"] = str(exc)[:1000]
    return result


def policy(requested="auto", *, info=None, batch_limit=None, compact=False):
    if requested not in ("auto", "cpu", "gpu", "cuda"):
        raise ValueError("Ungültiges Transkriptionsgerät.")
    if requested == "cpu":
        return dict(device="cpu", compute="int8", batch=4, reason="CPU ausdrücklich ausgewählt")
    info = probe() if info is None else info
    if not info["ready"]:
        reason = info.get("ct2Error") or "CUDA nicht verfügbar"
        if requested != "auto":
            raise RuntimeError("GPU angefordert, aber nicht nutzbar: " + reason)
        return dict(device="cpu", compute="int8", batch=4, reason="CPU-Fallback: " + reason)
    types, free = info["computeTypes"], info.get("freeMb", 0)
    preferred = ("int8_float16", "float16", "float32") if compact or free < 6000 else ("float16", "int8_float16", "float32")
    compute = next((kind for kind in preferred if kind in types), types[0])
    batch = 16 if free >= 12000 else 8 if free >= 6000 else 2
    if batch_limit is not None:
        batch = min(batch, batch_limit)
    return dict(device="cuda", compute=compute, batch=batch,
                reason=f"{info.get('deviceName', 'NVIDIA')} · {free} MB frei")


def gpu_failure(exc):
    message = str(exc).lower()
    if "out of memory" in message or "cublas_status_alloc_failed" in message:
        return "oom"
    if any(term in message for term in ("cuda", "cudnn", "cublas", "nvidia", "no kernel image", "driver version")):
        return "cuda"
    return None


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=True))
