"""Load the real CUDA wheel DLLs on Windows CI, without requiring a GPU."""
import ctypes
import os
from pathlib import Path
import sys

from whisperx_studio.gpu_runtime import prepare_cuda

assert os.name == 'nt'
paths = prepare_cuda()
assert paths, 'No managed CUDA DLL paths registered'
import torch
import ctranslate2

assert torch.version.cuda == '12.8', torch.__version__
for name in ('cublas64_12.dll', 'cublasLt64_12.dll', 'cudnn64_9.dll'):
    location = next((Path(p) / name for p in paths if (Path(p) / name).is_file()), None)
    assert location, f'{name} missing in {paths}'
    ctypes.WinDLL(str(location))
    print(f'Loaded {location}')
print('Real Windows CUDA DLL bootstrap passed; GPU execution requires NVIDIA hardware.')
