# WinWhisper Studio v1.0.2 — GPU-Diagnose und Windows-Build

## Neu
- Live-Diagnose unter **Einrichtung** mit NVIDIA-Modell, Treiberversion, VRAM-Belegung und gemessener GPU-Gesamtauslastung.
- Diagnostik der nativen WhisperX-Laufzeit mit PyTorch-CUDA, CTranslate2-GPU-Erkennung und tatsächlich gewähltem Transkriptionsmodus.
- Lokale Ollama-Diagnose für geladene Modelle, inklusive GPU-/CPU-Speicherverteilung; Docker-Modus wird separat im eigenen Container abgefragt.
- Sichere, rein lesende Diagnose über einen isolierten Electron-IPC-Kanal. Messwerte werden nur bei geöffnetem Bereich abgerufen und ohne HTML-Injektion dargestellt.
- Neue Unit-/IPC-Tests für GPU, CPU-Fallback, Offline-Ollama und Docker-Engine. Windows-Installer weiterhin per GitHub Actions.

**Wichtig:** NVIDIA-Gesamtauslastung und Ollama-Modellspeicher sind Indikatoren; sie beweisen nicht für jeden Auftrag den tatsächlichen Rechenweg. Windows 11 / NVIDIA-Hardware muss zusätzlich praktisch getestet werden. Der Installer ist ohne Signaturzertifikat nicht signiert.
