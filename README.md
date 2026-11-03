# WinWhisper Studio

**Von Verwaltungen für Verwaltungen entwickelt.** WinWhisper Studio ist eine lokale
Anwendung zum Aufnehmen, Transkribieren und Dokumentieren von Besprechungen, Interviews,
Rats- und Ausschusssitzungen sowie persönlichen Notizen. Entwickelt von **Dominik Tröster,
Verbandsgemeinde Otterbach-Otterberg**.

**Open Source für alle:** Der Projektcode ist unter der [MIT-Lizenz](LICENSE)
veröffentlicht. WhisperX, Ollama, Docker und die heruntergeladenen Sprachmodelle sind
separate Projekte und gelten unter ihren jeweiligen Lizenzen beziehungsweise
Nutzungsbedingungen.

## Was die Anwendung kann

- Audio direkt unter Windows aufnehmen oder Audio- und Videodateien importieren.
- Aufnahmen als Waveform ansehen, anhören, zoomen, Anfang oder Ende kürzen und markierte
  Bereiche entfernen. Änderungen bleiben umkehrbar; die Quelldatei wird nicht überschrieben.
- Deutsch und Englisch transkribieren und Abschnitte sowie Sprecherzuordnungen korrigieren.
- Bei Bedarf bis zu 15 Sprecher unterscheiden. Die Diarisierung benötigt eine eigene
  Freigabe für das pyannote-Modell und einen persönlichen Hugging-Face-Lesetoken.
- Ausgewählte Auswertungen einzeln erstellen: ausführliches Protokoll, Zusammenfassung,
  Aufgabenliste mit belegter Sprecherzuordnung, Beschlüsse und Abstimmungen, Themen,
  offene Fragen oder Interviewauswertung.
- Markdown-Protokolle und Auswertungen speichern.

Die Aufnahme ist auf drei Stunden und 15 Minuten begrenzt. Die Auswertungen nutzen lokal
installiertes Gemma und Qwen. Sie können Fehler machen; Ergebnisse und Sprecherzuordnungen
sollten vor der Verwendung geprüft werden.

## Installation unter Windows

1. Öffne [Actions → Windows installer](https://github.com/derdigitalaffine/winwhisper/actions/workflows/windows-build.yml)
   und lade im jüngsten erfolgreichen Lauf das Artefakt `WinWhisper-Windows-x64` herunter.
   Das Artefakt enthält das Setup und eine SHA-256-Prüfsumme. Zum Herunterladen ist ein
   GitHub-Konto mit Leserechten für das Repository erforderlich. GitHub bewahrt Artefakte
   standardmäßig 90 Tage auf.
2. Entpacke das Artefakt und starte `WinWhisper-Studio-1.0.0-Setup-x64.exe`.
3. Beim ersten Start öffnet sich der Einrichtungsassistent. **Windows nativ** ist der
   empfohlene Standard und benötigt weder WSL noch Docker Desktop. WinWhisper richtet eine
   eigene Python-3.12-Umgebung im Benutzer-Arbeitsordner ein. Fehlt Python 3.12 x64, versucht
   die App die Benutzerinstallation über `winget`.
4. Ollama ist nur für Protokolle und andere Auswertungen nötig. Aufnahme und WhisperX-
   Transkription funktionieren ohne Ollama. Im Assistenten kann Ollama optional als native
   Windows-Anwendung für den aktuellen Benutzer installiert werden.

Die native Laufzeit installiert WhisperX in einer isolierten virtuellen Python-Umgebung
innerhalb des WinWhisper-Arbeitsordners. FFmpeg wird über ein Python-Paket bereitgestellt;
eine systemweite FFmpeg-Installation ist nicht erforderlich. Sprachmodelle werden erst bei
Bedarf lokal heruntergeladen. Die erste Einrichtung benötigt mehrere Gigabyte freien
Speicher und eine Internetverbindung.

Bei `Automatisch` prüft WinWhisper zuerst, ob eine NVIDIA-GPU vorhanden ist. Die CUDA-
Laufzeit wird anschließend mit PyTorch **und** CTranslate2 getestet. Wenn der GPU-Test
scheitert, bleibt der Automatikmodus auf CPU nutzbar. `NVIDIA-GPU erforderlich` behandelt
einen fehlgeschlagenen GPU-Test dagegen als Fehler. Eine NVIDIA-GPU ist nicht erforderlich.

### Docker / WSL 2 als Kompatibilitätsmodus

Der bisherige Docker-Pfad bleibt verfügbar, ist aber nicht mehr der Standard. Im
Einrichtungsassistenten kann unter **Lokale Laufzeit** auf `Docker / WSL 2 · erweitert`
gewechselt werden. Dieser Modus benötigt weiterhin WSL 2, Docker Desktop und Linux-
Container. Er ist als Rückfalloption gedacht, falls die native Windows-Laufzeit auf einem
bestimmten Rechner nicht eingesetzt werden kann.

Die Anwendung veröffentlicht in keinem Modus einen Whisper-Port im Windows-Netzwerk.
Aufnahmen und Transkripte werden nicht zur Verarbeitung an einen externen Dienst gesendet.
Im nativen Modus startet WinWhisper Ollama – sofern installiert – lokal für die
Auswertungsfunktionen. Internet wird für die Ersteinrichtung, Modell-Downloads und
gegebenenfalls noch fehlende Sprach- oder Ausrichtungsmodelle benötigt.

## Einen Windows-Build erstellen

Ein erfolgreicher Lauf des GitHub-Actions-Workflows erstellt das x64-Setup automatisch
bei einem Push auf `main`. Pull Requests führen denselben Windows-Test- und Buildpfad aus.
Ein Build kann außerdem manuell über **Actions → Windows installer → Run workflow**
gestartet werden. Das Setup und die Prüfsumme liegen danach beim jeweiligen Workflow-Lauf
als Artefakt; sie werden nicht automatisch als dauerhafte GitHub-Veröffentlichung angelegt.

Alternativ lässt sich das Setup auf Windows 11 x64 lokal bauen:

```powershell
.\Windows-Setup-bauen.cmd
```

**Ohne vorheriges Klonen:** Öffne PowerShell im Zielordner und führe diese einzelne
Zeile aus. Sie lädt das Skript direkt aus dem Repository, lädt den Quellcode temporär
herunter, prüft ihn, baut das Setup und legt Setup samt Prüfsumme im aktuellen Ordner ab:

```powershell
irm https://raw.githubusercontent.com/derdigitalaffine/winwhisper/main/Build-WinWhisper.ps1 | iex
```

Das Skript benötigt Windows x64 und eine Internetverbindung. Wenn Node.js 22 oder neuer
fehlt, versucht es die Installation über winget; dabei kann ein Installationsdialog
erscheinen. Der temporäre Quellcode und die Build-Abhängigkeiten werden nach dem Build
entfernt. Vor dem Packaging laufen die JavaScript-Unit-Tests und die Quellstrukturprüfung.

Voraussetzungen für den Build: Node.js 22 oder neuer, npm, Windows x64 und eine
Internetverbindung für die Build-Abhängigkeiten. Das Ergebnis liegt in `dist/`. Die
Setup-Datei ist ohne ein Signaturzertifikat unsigniert.

Der App-Build ist vom Bau beziehungsweise Download der KI-Laufzeit getrennt. Die native
Python-Umgebung, WhisperX und Modelle werden erst beim Einrichten auf dem Zielrechner
installiert. Dadurch bleibt das eigentliche Windows-Setup klein. Der optionale Docker-Modus
erstellt sein Image ebenfalls erst auf dem Zielrechner.

## Entwicklung

```sh
npm ci
npm test
npm run verify:source
npm start
```

Das Windows-Setup lässt sich auf Windows mit `npm run dist:win` erstellen. Die native und
Docker-basierte KI-Engine liegen in `container/`, die Windows-Oberfläche in `desktop/` und
die Systemeinrichtung unter `scripts/`. Projekt-, Aufnahme- und Modelldaten bleiben im
lokalen Windows-Arbeitsordner der Anwendung.

## Prüfstand

Die plattformübergreifenden Softwareprüfungen decken Desktop-Runtime, IPC, Aufnahme,
Dateizugriff und die Auswahl zwischen nativer Windows- und Docker-Laufzeit ab. Der
GitHub-Actions-Build läuft auf einem Windows-Runner. Eine vollständige Abnahme auf einem
repräsentativen Verwaltungs-PC sollte zusätzlich CPU-Transkription, NVIDIA-GPU,
mehrstündige Aufnahme, Ollama-Auswertungen, Sprechertrennung sowie den Docker-Fallback
umfassen. Siehe [Prüfbericht](validation/Pruefbericht.md) und
[Windows-Abnahme](docs/Windows-Abnahme.md).

## Lizenz und Urheber

Copyright © 2026 Dominik Tröster, Verbandsgemeinde Otterbach-Otterberg.

Der hier enthaltene Projektcode wird unter der MIT-Lizenz angeboten. Die eingebundenen
und heruntergeladenen Drittprojekte sowie Sprachmodelle bleiben ihren eigenen Lizenzen,
Modellkarten und Nutzungsbedingungen unterstellt.
