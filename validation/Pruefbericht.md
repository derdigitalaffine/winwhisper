# Prüfstand vom 03.11.2026

Weitere Tests und der Container-Build wurden auf Nutzerwunsch beendet. Danach wurden keine
weiteren Tests, Builds oder GitHub-Workflows gestartet.

**105 Softwaretests bereits bestanden:** 33 Node-Tests, 63 Tests der Python-Engine und
9 Tests des Windows-Containeradapters. Die Testausgaben entstanden vor dem Stopp.
Electron, Docker und Mikrofon-APIs werden in diesen Softwaretests teilweise nachgebildet.
Die Python-Tests verwenden unter anderem echtes FFmpeg, Dateien und Unterprozesse.

Zusätzlich bereits durchgeführt:

- Windows-x64-Installer mit Electron Builder/NSIS erfolgreich unter Linux erzeugt.
- Vorab-Setup in einem separaten Wine-Präfix installiert. Wine hat einen nicht funktionsfähigen
  PowerShell-Platzhalter, der die Prozessprüfung des Installers verfälscht. Dieser wurde nur
  im Wegwerf-Präfix vorübergehend deaktiviert und danach wiederhergestellt. Der Installer
  wurde dafür nicht verändert. Installation danach mit Exitcode 0.
- Installierte Windows-EXE unter Wine geöffnet: sichere lokale Origin, Renderer und Preload-Brücke geladen.
- Oberfläche mit echtem Electron 43.8.6 geöffnet; Einrichtungsdialog visuell geprüft und
  Timingfehler beim ersten Start korrigiert.
- Chromium-Testmikrofon und echtes AudioWorklet liefern PCM-Pakete mit 3200 Bytes.
- Container-Abhängigkeiten installiert; `pip check`: „No broken requirements found“.
  Imageexport anschließend auf Nutzerwunsch abgebrochen. Kein Containerlauf und keine
  WhisperX-/Gemma-/Qwen-Inferenz in diesem neuen Image durchgeführt.

Der Vorab-Installer entstand vor den letzten Korrekturen am ersten Start und am lokalen
Entwicklungs-Pfad. Er ist daher kein Build des letzten Quellstands. Der aktuelle Stand
kann mit `Windows-Setup-bauen.cmd` oder dem manuellen GitHub-Workflow neu gebaut werden.
Dieser Workflow wurde nicht gestartet.

Die Abnahme auf echter Windows-Hardware bleibt offen; siehe `docs/Windows-Abnahme.md`.
Der vorbereitete Container-Integrationstest wurde nicht ausgeführt.

Die ursprüngliche Linux-App sowie vorhandene Aufnahmen und KI-Modelle wurden nicht verändert.
Große Build-/Testdownloads und temporäre Umgebungen wurden nach der GitHub-Übernahme entfernt.
Docker meldete dafür 29,25 GB gelöschten Build-Cache. Das lokale Vorab-Setup samt Prüfsumme bleibt erhalten.
Zugangstokens, Audiodateien und Modellgewichte werden nicht veröffentlicht.
