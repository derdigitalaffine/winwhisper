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
3. Beim ersten Start öffnet sich der Einrichtungsassistent. Er benötigt WSL 2 und Docker
   Desktop mit Linux-Containern. Folge dem Assistenten, um die lokale Laufzeit und die
   gewünschten Modelle herunterzuladen.

Das Setup installiert die Desktop-App für den aktuellen Windows-Benutzer. Es enthält
WhisperX und die Sprachmodelle nicht. Diese werden beim Einrichten über Docker und Ollama
lokal heruntergeladen. Die erste Einrichtung benötigt mehrere Gigabyte freien Speicher.
Die NVIDIA-GPU wird automatisch geprüft; wenn sie in Docker nicht verfügbar ist, verwendet
die Anwendung die CPU. Eine NVIDIA-GPU ist optional.

Die Anwendung veröffentlicht keinen Netzwerkport für ihre lokalen Modelle. Aufnahmen
und Transkripte werden nicht zur Verarbeitung an einen externen Dienst gesendet.
Internet wird für die Ersteinrichtung, Modell-Downloads und gegebenenfalls noch fehlende
Sprach- oder Ausrichtungsmodelle benötigt.

## Einen Windows-Build erstellen

Ein erfolgreicher Lauf des GitHub-Actions-Workflows erstellt das x64-Setup automatisch
bei einem Push auf `main`. Ein Build kann außerdem manuell über **Actions → Windows
installer → Run workflow** gestartet werden. Das Setup und die Prüfsumme liegen danach
beim jeweiligen Workflow-Lauf als Artefakt; sie werden nicht automatisch als dauerhafte
GitHub-Veröffentlichung angelegt.

Alternativ lässt sich das Setup auf Windows 11 x64 lokal bauen:

```powershell
.\Windows-Setup-bauen.cmd
```

**Ohne vorheriges Klonen:** Öffne PowerShell im Zielordner und führe diese einzelne
Zeile aus. Sie lädt das Skript direkt aus dem Repository, lädt den Quellcode temporär
herunter, baut das Setup und legt Setup samt Prüfsumme im aktuellen Ordner ab:

```powershell
irm https://raw.githubusercontent.com/derdigitalaffine/winwhisper/main/Build-WinWhisper.ps1 | iex
```

Das Skript benötigt Windows x64 und eine Internetverbindung. Wenn Node.js 22 oder neuer
fehlt, versucht es die Installation über winget; dabei kann ein Installationsdialog
erscheinen. Der temporäre Quellcode und die Build-Abhängigkeiten werden nach dem Build
entfernt. Das Skript führt keine Tests aus.

Voraussetzungen: Node.js 22 oder neuer, npm, Windows x64 und eine Internetverbindung für
die Build-Abhängigkeiten. Das Ergebnis liegt in `dist/`. Die Setup-Datei ist ohne ein
Signaturzertifikat unsigniert.

Der App-Build ist vom Bau der KI-Laufzeit getrennt: Docker erstellt WhisperX und Ollama
erst beim Einrichten auf dem Windows-Rechner. So muss das mehrere Gigabyte große Image
nicht für jeden App-Build erneut verteilt werden.

## Entwicklung

```sh
npm ci
npm start
```

Das Windows-Setup lässt sich auf Windows mit `npm run dist:win` erstellen. Die Docker-
Engine liegt in `container/`, die Windows-Oberfläche in `desktop/` und die Einrichtung
unter `scripts/`. Projekt-, Aufnahme- und Modelldaten bleiben im lokalen
Windows-Arbeitsordner der Anwendung.

## Prüfstand

Die plattformübergreifenden Softwareprüfungen wurden vor dem letzten README- und
Lizenzupdate ausgeführt. Nach einer späteren Bitte wurden weitere Tests und der Export
des Docker-Images gestoppt. Eine Abnahme auf einem echten Windows-Rechner, einschließlich
WSL, Docker-GPU und mehrstündiger Aufnahme, steht noch aus. Siehe
[Prüfbericht](validation/Pruefbericht.md) und [Windows-Abnahme](docs/Windows-Abnahme.md).

## Lizenz und Urheber

Copyright © 2026 Dominik Tröster, Verbandsgemeinde Otterbach-Otterberg.

Der hier enthaltene Projektcode wird unter der MIT-Lizenz angeboten. Die eingebundenen
und heruntergeladenen Drittprojekte sowie Sprachmodelle bleiben ihren eigenen Lizenzen,
Modellkarten und Nutzungsbedingungen unterstellt.
