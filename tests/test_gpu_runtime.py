"""GPU failure policy tests use fakes: no GPU, downloads or torch required."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from whisperx_studio import gpu_runtime as gpu

ENTRY = Path(__file__).resolve().parents[1] / 'container' / 'whisperx_cli.py'
spec = importlib.util.spec_from_file_location('gpu_cli', ENTRY)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def info(free=10000, types=None):
    return dict(ready=True, freeMb=free, computeTypes=types or ['float16', 'int8_float16', 'float32'], deviceName='Test GPU')


class GpuPolicyTests(unittest.TestCase):
    def test_gpu_precision_and_batches_follow_capability_and_memory(self):
        self.assertEqual(gpu.policy(info=info())['compute'], 'float16')
        self.assertEqual(gpu.policy(info=info())['batch'], 8)
        self.assertEqual(gpu.policy(info=info(4000))['compute'], 'int8_float16')
        self.assertEqual(gpu.policy(info=info(4000))['batch'], 2)
        self.assertEqual(gpu.policy(info=info(types=['float32']))['compute'], 'float32')
        self.assertEqual(gpu.policy(info=info(20000), batch_limit=1, compact=True)['batch'], 1)

    def test_explicit_cpu_never_probes_or_initializes_cuda(self):
        with patch.object(gpu, 'probe', side_effect=AssertionError('GPU touched')):
            self.assertEqual(gpu.policy('cpu')['compute'], 'int8')

    def test_auto_fallback_keeps_reason_and_explicit_gpu_errors(self):
        broken = dict(ready=False, ct2Error='cudnn64_9.dll fehlt')
        self.assertIn('cudnn64_9', gpu.policy(info=broken)['reason'])
        with self.assertRaisesRegex(RuntimeError, 'cudnn64_9'):
            gpu.policy('gpu', info=broken)

    def test_probe_initializes_a_real_kernel_and_rejects_architecture_failure(self):
        torch = types.SimpleNamespace(__version__='2.8+cu128', version=types.SimpleNamespace(cuda='12.8'),
            cuda=types.SimpleNamespace(is_available=lambda: True),
            ones=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('no kernel image is available')))
        with patch.dict(sys.modules, {'torch': torch}):
            result = gpu.probe()
        self.assertFalse(result['ready'])
        self.assertIn('kernel image', result['ct2Error'])

    def test_gpu_error_classifier_does_not_retry_network_or_input_failures(self):
        self.assertEqual(gpu.gpu_failure(RuntimeError('CUDA out of memory')), 'oom')
        self.assertEqual(gpu.gpu_failure(RuntimeError('Could not load cudnn64_9.dll')), 'cuda')
        self.assertIsNone(gpu.gpu_failure(RuntimeError('401 Unauthorized')))
        self.assertIsNone(gpu.gpu_failure(RuntimeError('Invalid audio')))

    def supervisor(self, args, codes):
        calls = []
        def launch(command, env, **_kwargs):
            calls.append((command, dict(env)))
            return next(codes)
        with patch.object(sys, 'argv', [str(ENTRY), *args]), patch.dict(os.environ, {}, clear=True), patch.object(cli, 'prepare_cuda'), patch.object(cli, 'run_worker', side_effect=launch), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as outcome:
                cli.main()
        return outcome.exception.code, calls

    def test_auto_retries_compact_gpu_then_cpu_in_fresh_processes(self):
        code, calls = self.supervisor(['audio.wav', '--studio-auto-device'], iter([75, 76, 0]))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]['WINWHISPER_COMPACT'], '1')
        self.assertEqual(calls[1][1]['WINWHISPER_BATCH_LIMIT'], '1')
        self.assertEqual(calls[2][1]['WINWHISPER_CPU_RETRY'], '1')

    def test_explicit_gpu_never_silently_runs_cpu_and_non_cuda_errors_stop(self):
        code, calls = self.supervisor(['audio.wav', '--studio-performance', '--device', 'cuda'], iter([76]))
        self.assertEqual((code, len(calls)), (76, 1))
        code, calls = self.supervisor(['audio.wav', '--studio-auto-device'], iter([1]))
        self.assertEqual((code, len(calls)), (1, 1))

    def test_native_cuda_abort_is_retried_but_unrelated_crash_is_not(self):
        for message, expected in [('Unable to load cudnn64_9.dll', 76), ('CUDA out of memory', 75), ('invalid audio', 3)]:
            child = types.SimpleNamespace(stdout=io.StringIO(message), wait=lambda: 3)
            with patch.object(cli.subprocess, 'Popen', return_value=child), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.run_worker(['python'], {}), expected)

    def test_worker_applies_selected_precision_and_removes_private_flags(self):
        captured = []
        fake = types.ModuleType('whisperx.__main__')
        fake.cli = lambda: captured.extend(sys.argv[1:])
        selected = dict(device='cuda', compute='float16', batch=8, reason='Test')
        with patch.object(sys, 'argv', [str(ENTRY), 'audio.wav', '--studio-auto-device', '--compute_type', 'int8', '--batch_size', '4']), patch.dict(os.environ, {'WINWHISPER_GPU_WORKER': '1'}, clear=True), patch.object(cli, 'prepare_cuda'), patch.object(cli, 'policy', return_value=selected), patch.dict(sys.modules, {'whisperx.__main__': fake}), contextlib.redirect_stderr(io.StringIO()):
            cli.main()
        self.assertNotIn('--studio-auto-device', captured)
        self.assertEqual(cli.option(captured, '--device'), 'cuda')
        self.assertEqual(cli.option(captured, '--compute_type'), 'float16')
        self.assertEqual(cli.option(captured, '--batch_size'), '8')

    def test_ollama_path_excludes_python_cuda_and_keeps_user_gpu_selection(self):
        import native_entry
        site = Path(sys.prefix) / 'Lib' / 'site-packages'
        paths = [str(site / 'torch' / 'lib'), str(site / 'nvidia' / 'cublas' / 'bin'), 'system-path']
        with patch.dict(os.environ, {'PATH': os.pathsep.join(paths), 'CUDA_VISIBLE_DEVICES': '-1'}), contextlib.redirect_stderr(io.StringIO()):
            env = native_entry._ollama_environment('/ollama/ollama.exe')
        self.assertEqual(env['PATH'].split(os.pathsep), [str(Path('/ollama')), 'system-path'])
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '-1')
        self.assertEqual(env['OLLAMA_NUM_PARALLEL'], '1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
