# WinWhisper Studio v1.0.1 — Windows compatibility update

This release focuses on a reliable Windows 11 x64 setup (including the Windows 11 26H2 compatibility target).

## Changes
- Fix native Python 3.12 / WhisperX setup readiness so a successful first-run installation is recognized.
- Repair interrupted Python environments without deleting existing recordings, projects, or models.
- Correct WhisperX CLI startup, including private FFmpeg provisioning for transcription.
- Support automatic CPU fallback when CUDA 12.8 / NVIDIA GPU compatibility checks fail.
- Restore Whisper model removal in Electron's trusted IPC interface.
- Restore Docker/WSL compatibility mode by building the missing engine image.
- Verify real Windows setup scripts and native AI entry points in GitHub Actions before publishing.

## Installation
Download the `WinWhisper-Studio-1.0.1-Setup-x64.exe` asset and its `.sha256` checksum.
Install on Windows 11 x64. At first start, choose **Windows nativ**, then **Windows-Laufzeit einrichten / reparieren**.
You can also choose the Docker/WSL fallback in the setup UI.

**Important:** The Windows installer is unsigned; Windows SmartScreen may show a warning. Do not bypass your organization's application policies. The first setup downloads Python/WhisperX model dependencies; native CPU transcription works without Docker or Ollama. Ollama is optional for report generation.

Automated validation uses Windows GitHub Actions runners. Windows 11 26H2-specific hardware acceptance (microphone, GPU drivers, managed endpoint restrictions, large models and long recordings) is not implied.
