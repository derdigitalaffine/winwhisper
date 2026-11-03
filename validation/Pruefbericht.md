# Prüfstand vom 03.11.2026

Der frühere Prüfstand bezog sich auf den Docker-/WSL-Entwurf. Seitdem wurde der Windows-Pfad
auf eine **native Standardlaufzeit** umgestellt; Docker / WSL 2 bleibt als optionaler
Kompatibilitätsmodus erhalten. Dieser Bericht beschreibt die nachweislich automatisiert
geprüften Ebenen. Er ersetzt weiterhin keine Abnahme auf repräsentativer Windows-Hardware.

## Aktuell automatisiert geprüft

Der Pull Request `native-windows-runtime` wird auf einem echten GitHub-Windows-Runner geprüft.
Der Workflow umfasst inzwischen:

- Python-3.12-Quellkompilierung der nativen Adapter und Smoke-Tests.
- JavaScript-/Node-Tests für Runtime-Auswahl, IPC, Dateigrenzen, Aufnahme und Renderer.
- echten Windows-x64-Installer-Build mit Electron Builder/NSIS und Artefakt-Upload.
- Aufbau einer isolierten Python-3.12-venv wie auf dem Zielrechner.
- Installation des CPU-PyTorch-Stacks sowie WhisperX 3.8.6, faster-whisper 1.2.1,
  CTranslate2 4.8.4 und pyannote.audio 4.0.7.
- Start und geordneten Shutdown des nativen Python-Hintergrunddienstes ohne Ollama.
- das private FFmpeg aus `imageio-ffmpeg`, ohne systemweite FFmpeg-Installation.
- Imports der nativen KI-Engine und den tatsächlichen WhisperX→pyannote-Pfad mit einer
  In-Memory-Waveform. Damit wird nicht fälschlich TorchCodecs optionaler Dateidecoder zur
  Voraussetzung der Sprechertrennung gemacht.
- Windows-Service-Tests für Aufnahme, Einstellungen, optionale Ollama-Nutzung,
  Pfadbegrenzung und Fehlerbehandlung. Der CI-Test stellt dafür dasselbe private
  `ffmpeg.exe` bereit, das auch der native App-Start verwendet.
- portable `/data/...`-Pfade an der Electron/Python-Grenze inklusive Traversal-Schutz.

Der zusätzliche Native-Engine-Smoke-Test hat einen realen Windows-Sonderfall sichtbar gemacht:
TorchCodec 0.7 kann seinen optionalen Dateidecoder ohne passende Shared-FFmpeg-DLLs nicht laden.
WhisperX 3.8.6 übergibt der pyannote-Diarisierung jedoch bereits dekodiertes Audio als
`waveform`/`sample_rate`. Dieser reale Anwendungspfad wurde im Windows-CI erfolgreich ausgeführt.
Eine zuvor versuchte zusätzliche Shared-DLL-Bootstrap-Lösung wurde deshalb wieder entfernt;
der App-Start lädt keine zusätzliche FFmpeg-Laufzeit aus einem separaten S3-Archiv nach.

Auch ein Testumgebungsfehler wurde durch den erweiterten Windows-Smoke-Test gefunden: Die
Service-Tests hatten `ffmpeg` aufgerufen, ohne zuvor das private Binary auf den Test-PATH zu
legen. Der Workflow wurde an den echten App-Start angeglichen, statt die Produktionslogik
abzuschwächen.

## Bereits früher geprüft

- Windows-x64-Installer mit Electron Builder/NSIS erzeugt.
- Vorab-Setup in einem separaten Wine-Präfix installiert und die installierte EXE geöffnet.
- sichere lokale Origin, Renderer und Preload-Brücke geprüft.
- Oberfläche mit echtem Electron geöffnet und den Einrichtungsdialog geprüft.
- Chromium-Testmikrofon und AudioWorklet mit PCM-Paketen geprüft.
- Docker-Abhängigkeiten und `pip check` im früheren Containerpfad geprüft.

Diese älteren Prüfungen bleiben als Entwicklungsnachweise relevant, sind aber kein Ersatz für
den aktuellen Windows-CI-Pfad und keine Freigabe des neuen nativen Laufzeitmodus.

## Noch offen vor einer Freigabe

Auf echter Windows-11-Hardware bleiben insbesondere CPU-End-to-End-Transkription mit realem
Modelldownload, NVIDIA/CUDA auf realer GPU, physische Mikrofone und Gerätewechsel,
mehrstündige Aufnahme, Hugging-Face-Modellfreigabe und echte Sprechertrennung, Ollama-Auswertungen
sowie der Docker-/WSL-Fallback zu prüfen. Die vollständige Liste steht in
`docs/Windows-Abnahme.md`.

Die ursprüngliche Linux-/Docker-Laufzeit bleibt im Repository als Fallback erhalten. Vorhandene
Aufnahmen und KI-Modelle werden durch den Quellumbau nicht absichtlich verändert. Zugangstokens,
Audiodateien und Modellgewichte werden nicht veröffentlicht.
