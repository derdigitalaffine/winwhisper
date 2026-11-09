# WinWhisper Studio v1.0.3 — automatische NVIDIA-Nutzung

- Einheitliche Windows-CUDA-Vorbereitung für Setup, Diagnose, Live- und WhisperX-Prozesse: verwaltete PyTorch-/NVIDIA-DLL-Verzeichnisse werden vor den KI-Imports registriert und bleiben geöffnet.
- Automatische Reparatur alter v1.0.2-CPU-Installationen beim Start, wenn NVIDIA erkannt wird. Die erste Reparatur lädt CUDA-Pakete herunter. Neu ausdrücklich gewählte CPU-Einrichtungen bleiben erhalten.
- CUDA-Prüfung mit echter PyTorch-Kernel-Ausführung, explizitem Laden von cuBLAS/cuDNN und CTranslate2-Fähigkeitsprüfung. Ein fehlgeschlagener GPU-Test entfernt die CUDA-Pakete nicht mehr dauerhaft.
- WhisperX wählt unterstützte GPU-Präzision (float16 oder bei wenig VRAM int8_float16) und Batchgröße nach freiem Speicher. CPU verwendet int8. Auftragsprotokolle nennen Gerät, Präzision, Batchgröße und Fallback-Grund.
- Bei GPU-Speichermangel folgt ein kompakter GPU-Versuch in einem neuen Prozess; im Automatikmodus ist anschließend CPU-Fallback möglich. Expliziter GPU-Modus meldet Fehler. Netzwerk-, Audio- und Modellzugriffsfehler werden nicht als GPU-Fehler wiederholt.
- Live-Transkription berücksichtigt die Geräteauswahl und fängt CUDA-Fehler auch während der verzögerten Dekodierung ab.
- Privater Ollama-Dienst mit eigenem DLL-Suchpfad, einer parallelen Anfrage und ausführlichem lokalem GPU-Startprotokoll. Modelle bleiben zwischen Auswertungsabschnitten geladen und werden nach der Auswertung bzw. vor WhisperX entladen. Geräte-Overrides werden protokolliert; CPU/GPU-/Hybrid-Modellspeicher wird vor dem Entladen gemeldet.
- Windows-CI prüft CPU-Setup, Startprozesse und echte CUDA-Wheel-DLLs. Release erfolgt erst nach allen drei erfolgreichen Prüfjobs und Installer-Prüfsummenprüfung.

CI ohne NVIDIA-Hardware kann GPU-DLLs und Fehlerübergänge prüfen, aber keine echte GPU-Transkription oder Beschleunigungsrate belegen. Ein Hardwaretest auf dem Zielrechner bleibt erforderlich. Der Installer ist nicht digital signiert.
