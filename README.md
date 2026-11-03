# WinWhisper Studio für Windows

Windows-Port der lokalen WhisperX-Anwendung, Stand 03.11.2026.

**Stand:** Quellprojekt für Windows 11 x64 mit Electron-Oberfläche, Windows-Aufnahme,
WhisperX-/Ollama-Container und NSIS-Setup. Ein Vorab-Installer wurde erfolgreich gebaut.
Die weiteren Tests und der noch laufende Container-Imageexport wurden auf Nutzerwunsch
beendet. Der letzte Quellstand enthält zusätzliche Korrekturen gegenüber diesem Vorab-Installer.
Die echte Windows-/WSL-/Hardware-Abnahme steht aus; Details unter `validation/`.

Der vollständige Quellstand liegt in [derdigitalaffine/winwhisper](https://github.com/derdigitalaffine/winwhisper).
Große Downloads, Modellgewichte, Testumgebungen und Build-Ausgaben gehören nicht ins Git-Repository.
Das Setup für den aktuellen Quellstand lässt sich mit dem folgenden Skript oder dem manuellen
[Windows-Workflow](https://github.com/derdigitalaffine/winwhisper/actions/workflows/windows-build.yml) bauen.
Der Workflow wurde hier nicht gestartet.

## Setup-Datei bauen

1. Diesen kompletten Ordner auf einen Windows-11-x64-PC kopieren bzw. das Quellarchiv entpacken.
2. **`Windows-Setup-bauen.cmd` doppelklicken.** Wenn Node.js fehlt, wird dessen offizieller
   Windows-Paketinstaller über winget aufgerufen. Installationsdialoge sind zu bestätigen.
3. Das Skript lädt die festgelegten Electron-/Builder-Versionen, führt Tests aus und erzeugt
   `dist/WinWhisper-Studio-1.0.0-Setup-x64.exe` samt SHA-256-Datei.
4. Das Setup installieren. Der eigentliche Nutzer braucht anschließend weder Node.js
   noch eine eigene Python-Installation.

Alternativ in PowerShell:

```powershell
.\scripts\Build-Windows.ps1 -InstallNode
```

Ohne Signaturzertifikat entsteht ein unsigniertes Setup. Eine signierte Veröffentlichung
erfordert ein eigenes Zertifikat bzw. einen eingerichteten Signierungsdienst.
Der Quellcode ist auf GitHub abgelegt. Installer werden nicht automatisch veröffentlicht.
Der mitgelieferte GitHub-Actions-Workflow wird ausschließlich manuell gestartet;
er wurde hier nicht ausgeführt.

## Erster Start auf Windows

Der Einrichtungsassistent ist auch später links über **Einrichtung** erreichbar.

1. Bei Bedarf **WSL 2 einrichten**, dann **Docker Desktop installieren**.
   Die Systemaktivierung kann Administratorbestätigung und einen Windows-Neustart erfordern.
   Die App startet den Rechner nicht eigenständig neu. Docker-Bedingungen werden im Docker-Installer angezeigt.
2. **Docker Desktop starten**, auf dessen Bereitschaft warten und Linux-Container / WSL 2 verwenden.
3. **WhisperX und Ollama einrichten** klicken. Ein lokales Image wird erstellt.
   CUDA-, Python- und KI-Abhängigkeiten laden mehrere GB; ausreichend freien Speicher einplanen.
4. Automatisch wird NVIDIA getestet; bei fehlender GPU-Unterstützung wird CPU verwendet.
   **NVIDIA-GPU erforderlich** bricht bei einem fehlgeschlagenen GPU-Test mit einer Meldung ab.
5. **Whisper small laden** für Live-Text, **Gemma e2b laden** für Protokolle.
   **Qwen 14B** ist optional und benötigt mehr RAM/VRAM. Downloads laufen einzeln.
6. Für Sprechertrennung über die Transkriptionseinstellungen die Hugging-Face-Modellfreigabe
   erledigen und einen eigenen Read-Token eintragen. Die Freigabe kann die App nicht stellvertretend erteilen.

Nach erfolgreicher Einrichtung startet die App ihren Container beim nächsten Öffnen selbst.
Docker Desktop muss laufen. Bei einem Dienstausfall **Aktivitätsprotokoll → Verbindung prüfen**
wählen; das zuletzt geöffnete, gespeicherte Projekt wird wiederhergestellt. Bei einem ausgefallenen Ollama innerhalb des noch laufenden Containers hilft **Einrichtung → Umgebung neu starten**. Vorher laufende Aufträge beenden.

## Aufnehmen, schneiden und auswerten

Die Oberfläche übernimmt Waveform, Zoom, Bereich entfernen, Zuschneiden, gespeichertes Rückgängig,
Text-/Sprecherkorrekturen, Markdown-Export und die sieben einzeln anforderbaren Auswertungsarten.
Gemma und Qwen können denselben gewählten Auftrag nacheinander bearbeiten.

Die Mikrofonaufnahme läuft **direkt unter Windows**, nicht über Linux-Audiogeräte.
PCM-Audio wird paketweise als 16-kHz-Mono-WAV geschrieben. Der Dateikopf wird regelmäßig aktualisiert
und synchronisiert. Nach einem Absturz werden unvollständige Dateiköpfe beim nächsten Start anhand der geschriebenen PCM-Daten repariert. Es wird kein Drei-Stunden-Audiopuffer im RAM angesammelt.
Live-Text verarbeitet dieselbe wachsende Datei; nach Stoppen kann die genaue WhisperX-Verarbeitung folgen.
Die Aufnahmegrenze beträgt 3 Stunden 15 Minuten; die Oberfläche meldet bei Erreichen einen Fehler und stoppt.

Die Oberfläche und alle Modellanfragen arbeiten lokal. Der Container veröffentlicht **keinen Port**;
die Desktop-App spricht mit ihm über stdin/stdout. Ollama ist nur innerhalb des Containers erreichbar.
Internet wird für Erstinstallation, Modell-Downloads und gegebenenfalls noch fehlende Sprach-/Alignmodelle benötigt.
Vollständiger Offline-Betrieb muss für die gewünschten Sprachen/Modelle nach diesen Downloads getestet werden.

## Daten und Updates

**Einrichtung → Arbeitsordner im Explorer öffnen** zeigt den Speicherort, standardmäßig:

```text
%APPDATA%\WinWhisper Studio\workspace\
  recordings\     originale Windows-Aufnahmen
  imports\        lokale Kopien geöffneter Audio-/Video-/Projektdateien
  projects\       Vorschauen, Projektdateien, Schnittgeschichte, Auswertungen
  models\         Whisper-/Hugging-Face-/Ollama-Caches
  home\           Token-Cache und WhisperX-Rohergebnisse
  logs\           Ollama-Diagnose
```

Die genaue Position wird im Assistenten angezeigt. Modelle, Aufnahmen und Projekte bleiben bei
Deinstallation der Oberfläche erhalten. Ein Container-Neustart löscht diese Daten nicht.
Vor Updates und zum Umzug den **gesamten Arbeitsordner** sichern.

Beim Import werden externe Dateien kopiert, damit der Container nur den eigenen Arbeitsordner sieht.
Originaldateien bleiben geschützt; diese Kopien benötigen zusätzlichen Speicherplatz.
Einzelne exportierte Projektdateien verweisen auf Dateien im Arbeitsordner und sind **kein vollständiges Archiv**.
Beim Umzug auf einen anderen PC müssen deshalb die zugehörigen Daten mitgenommen werden.
Die frühere Linux-App hat andere absolute Pfade: für deren Projekte Audio und Transkript importieren;
eine automatische vollständige Linux-Projektmigration ist noch nicht enthalten.

## Technik und Prüfung

```text
desktop/       Electron-Oberfläche, Windows-PCM-Aufnahme, Container-/Dateibrücke
container/     WhisperX 3.8.6, Torch 2.8.0, Ollama 0.40.14, Protokoll-Pipeline
scripts/       Windows-Build, Systemeinrichtung, Strukturprüfung
tests/         Node-Tests ohne externe Pakete, Windows-Service-Tests
docs/          Bedienkonzept, Promptrecherche, Windows-Abnahme
validation/    Tatsächliche Testergebnisse und verbleibende Grenzen
```

```sh
node scripts/verify-source.cjs
npm test
```

Container-Build: `docker build -t winwhisper/engine:1.0.0 container`.
Die App erledigt dies auf dem Zielrechner; das Image ist nicht im kleinen App-Installer enthalten.
Direkte Abhängigkeiten sind festgelegt; für transitive Abhängigkeiten liegen zusätzlich Versions-Constraints aus der funktionierenden Linux-Python-3.12-Umgebung bei. Die beim Imagebau aufgelösten transitiven Versionen
werden als `/app/requirements.resolved.txt` im Image dokumentiert; ein vollständig auf einem
echten Windows-/Docker-Rechner validierter Lockstand steht noch aus.

Die bisherige Linux-Anwendung unter `~/.local/share/local-ai` wird durch dieses Projekt nicht geändert.
Die ältere Anleitung in `docs/WhisperX-Studio.md` beschreibt die übernommenen Editor-/Auswertungsfunktionen;
für Windows-Installation, Pfade und Aufnahme gilt diese README.

Aktueller Softwareprüfstand: **33 Node-Tests + 72 Python-Tests bestanden**. Details und Systemgrenzen: [Prüfbericht](validation/Pruefbericht.md).
