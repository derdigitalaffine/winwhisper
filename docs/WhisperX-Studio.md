# WhisperX Studio · Desktop 2.0

Start: **Anwendungen → KI → WhisperX Studio** oder `whisperx-gui`.
Ein noch geöffnetes altes Fenster bitte schließen und die Anwendung über den Starter neu öffnen.
Die neue Oberfläche läuft als eigene Electron-Desktopanwendung mit lokalem Python-Hintergrunddienst.

## Aufnehmen und bearbeiten

1. Oben **Datei öffnen** wählen oder **Aufnehmen** drücken.
2. Bei einer Aufnahme Mikrofon und bei Bedarf Live-Text auswählen, dann **Aufnahme starten**.
3. Mit **Aufnahme beenden** wird das Audio gespeichert und in den Arbeitsbereich geladen.
4. Ein Klick in die Waveform setzt die Wiedergabeposition. Ziehen markiert einen Bereich.
5. Die Schere entfernt den markierten Bereich; das Zuschneidesymbol behält nur die Auswahl.
6. Die Zeitfelder einer Auswahl erlauben genaue Grenzen als `hh:mm:ss.mmm`.
7. **Rückgängig** stellt Schnitte und ein zuvor vorhandenes Transkript wieder her, auch nach dem erneuten Öffnen des Projekts.

Zoom und Zeitachsenschieber helfen bei langen Sitzungen. **Gesamt** zeigt wieder die ganze Aufnahme.
Die Wiedergabegeschwindigkeit ist zwischen 0,5× und 2× wählbar. Bei einer markierten Auswahl
beginnt die Wiedergabe gegebenenfalls an deren Anfang und endet an ihrer Endgrenze.

Das Original bleibt erhalten. Ein Schnitt setzt das aktuelle Transkript zurück, weil dessen
Zeitmarken sonst nicht mehr passen. Danach neu transkribieren oder den Schnitt rückgängig machen.
Vorhandene Auswertungen bleiben erhalten und werden bei geänderter Grundlage als älterer Stand markiert.

Über **… → Bearbeitete Audiofassung exportieren** entsteht eine WAV-Datei mit ursprünglicher
Kanalzahl und Abtastrate als PCM mit 16 Bit. Die interne Arbeitskopie verwendet 16 kHz mono;
sie liegt auf der Festplatte. Drei Stunden benötigen dafür ungefähr 346 MB und rund 4,3 MB
Waveform-Spitzenwerte im Speicher, zuzüglich Projekt- und Arbeitsdaten.

## Transkribieren

Die Einstellungen sitzen links unten im Bereich **Transkription**. Das Zahnrad öffnet die
Sprachauswahl, Modellgröße, GPU-/CPU-Auswahl und Sprechertrennung. Deutsch und Englisch sind
vorbereitet; automatische Spracherkennung ist ebenfalls wählbar.

**Transkribieren** verarbeitet die aktuelle Audiofassung. Bei bekannter Sprecherzahl sind
1–15 wählbar; automatisch wird auf höchstens 15 Sprecher begrenzt. Die automatische
Sprechertrennung liefert Labels, keine echten Namen. Überlappende Stimmen können Fehler verursachen.
Größere Whisper-Modelle brauchen mehr Zeit und Speicher und gegebenenfalls einen ersten Download.

Für die Sprechertrennung gegebenenfalls einmalig **Sprechermodell einrichten** öffnen.
Die vorhandene Einrichtung führt über die Hugging-Face-Modellfreigabe und einen lokal eingegebenen
Read-Token. Das Programm akzeptiert keine Modellbedingungen stellvertretend.

## Text und Sprecher korrigieren

Die Transkriptkarten zeigen Sprecher, Zeitbereich und Gesagtes. Wähle eine Karte, um rechts
Text und Sprecher zu bearbeiten. Änderungen werden automatisch gespeichert. Doppelklick auf
eine Karte oder **Anhören** im Korrekturbereich springt zum passenden Audioabschnitt.

Das Personensymbol öffnet **Stimmen bekommen Namen**. Namen gelten für diese Aufnahme.
Über **Sprecher hinzufügen** lassen sich auch manuell weitere Sprecher anlegen; anschließend
können einzelne Abschnitte über die Auswahl im Korrekturbereich zugewiesen werden.

Die Suche findet Text, Sprecherlabels und vergebene Namen. Große Transkripte laden beim
Scrollen weitere Karten nach. Das Downloadsymbol über dem Transkript exportiert Markdown.
**… → WhisperX-Transkript importieren** lädt ältere JSON-Ergebnisse; es muss dieselbe Audiofassung sein.

## Eine passende Auswertung anfordern

1. Unter **Auswertungen** auf **Neue Auswertung** klicken.
2. Genau eine gewünschte Art auswählen.
3. Gemma oder Qwen wählen, optional einen Vergleich mit einem zweiten Modell aktivieren.
4. Detailgrad, Ausgabesprache und bei Bedarf Schwerpunkt einstellen.
5. Zusätzliche Belegprüfung und Fundstellen im Markdown nach Bedarf aktivieren.
6. Den gewählten Auftrag starten. Weitere Arten können später separat angefordert werden.

Verfügbar sind:

- **Ausführliches Protokoll:** gut formulierter Fließtext mit Begründungen, Gegenpositionen und Ergebnissen.
- **Ergebnisprotokoll:** Ergebnisse, Festlegungen und offene Punkte ohne vollständige Nacherzählung.
- **Verlaufsprotokoll:** chronologischer Verlauf mit belegten Sprecherpositionen.
- **Zusammenfassung:** kompakter Gesamtüberblick, auch bei langen Sitzungen.
- **Aufgabenliste:** konkrete Aufgaben mit Zuständigen bzw. angefragten Personen, Status und genannten Terminen.
- **Beschlüsse & Abstimmungen:** ausdrücklich genannte Beschlüsse, Status und Abstimmungsergebnisse.
- **Interviewauswertung:** tatsächlich gestellte Fragen, zugehörige Antworten und zentrale Positionen.

Es werden **nicht automatisch alle Arten erzeugt**. Ein ausführliches Protokoll enthält keine
zusätzlich erzeugte Aufgabenliste oder Kurzfassung. Eine Aufgabenanforderung erstellt kein allgemeines Protokoll.

Im Modellvergleich bearbeiten beide Modelle denselben Auftrag nacheinander. Fertige Ergebnisse
werden nebeneinander angezeigt; über das Spaltensymbol lässt sich die Einzelansicht wählen.
Jedes Ergebnis hat einen eigenen Markdown-Export. Frühere Ergebnisse bleiben in der Liste erhalten.

Titel, Sitzungsdatum und Tagesordnung lassen sich über den Stift neben dem Sitzungstitel bearbeiten.
Ein Schwerpunkt lenkt die Auswertung, ist aber keine Quelle für zusätzliche Fakten.

## Belege und lange Sitzungen

Jede Aussage soll durch wörtliche Belege mit Segment-IDs gestützt sein. Die Anwendung prüft
Originalzitate, Zuständigkeits- und Terminbelege. Eine zusätzliche, standardmäßig aktive zweite
Modellprüfung bewertet den Inhalt am Transkript. Aufgaben unterscheiden Anfragen, Aufträge,
Zusagen, offene Zuständigkeiten und Rücknahmen. Relative Termine bleiben im genannten Wortlaut stehen.
Späte ausdrückliche Rücknahmen werden zusätzlich mit früheren Zusagen abgeglichen.

Bei einer Zusammenfassung werden die Abschnittsergebnisse zum Gesamtüberblick verdichtet.
Ausführliche Protokolle behalten dagegen ihre ausführlichen Abschnitte. Kurze Nachbarbeiträge
liefern Kontext an Abschnittsgrenzen. Fertige Abschnitte werden gespeichert und bei identischem
Auftrag nach einem Abbruch weiterverwendet.

**Abbrechen** beendet den laufenden Auftrag. Aufnahme, Projekt und bereits fertige
Analyseabschnitte bleiben erhalten. Ein abgebrochener Vergleich kann bereits ein vollständiges
Ergebnis des ersten Modells enthalten.

Fundstellen im Leser führen zum Audio. Im Markdown führen sie zu den Originalauszügen im Dokument.
Bei einem älteren Projektstand bleiben die alten Belege im Export nachlesbar; ein Sprung in die
inzwischen geänderte Zeitachse wird verhindert.

Ausgaben bleiben KI-Entwürfe. Auch eine zweite Modellprüfung garantiert keine Richtigkeit.
Beschlüsse, Stimmenzahlen und Zuständigkeiten sollten an den Fundstellen geprüft werden.
Die detaillierte Recherche, Promptregeln und Prüffälle stehen im
[Promptkonzept](WhisperX-Promptkonzept.md).

## Live-Text und Mikrofon

Live-Text ist eine vorläufige Vorschau. Die abschließende WhisperX-Verarbeitung erstellt
bei aktivierter Nachbearbeitung nach dem Stoppen genauere Zeitmarken und die optionale Sprechertrennung.
Nicht nachbearbeiteter Live-Text wird als vorläufig markiert.

Die aktuelle Oberfläche kann vorhandene Audio-/Videodateien laden und Mikrofonaufnahmen
starten. Das konkrete Mikrofon und die Audioausgabe müssen im laufenden Desktop funktionieren.
Originalaufnahmen liegen weiterhin unter `~/Musik/WhisperX-Aufnahmen/`.

## Projekte und Bibliothek

Jeder Import erhält ein automatisch gespeichertes Projekt. Die Seitenleiste zeigt zuletzt
bearbeitete Projekte; **Bibliothek** öffnet die Übersicht. **… → Projektdatei öffnen** lädt
andere `.whisperx.json`-Dateien. **… → Projekt speichern unter** speichert zusätzlich eine Projektdatei.

Die Projektdatei verknüpft Original und Arbeitskopie. Sie ist kein einzelnes Audioarchiv;
beim Umzug müssen die verknüpften Dateien mitgenommen werden. Veränderte Originaldateien
werden erkannt und müssen neu importiert werden. Bestehende Projekte und frühere
Gesamtauswertungen bleiben lesbar.

| Inhalt | Ort |
|---|---|
| Projekte, Vorschau, Schnittgeschichte, Auswertungscaches | `~/.local/share/local-ai/whisperx-studio/projects/` |
| Original-Mikrofonaufnahmen | `~/Musik/WhisperX-Aufnahmen/` |
| WhisperX-Rohergebnisse | `~/Dokumente/Transkripte/` |
| Desktopoberfläche | `~/.local/share/local-ai/whisperx_studio/desktop/` |
| Lokaler Hintergrunddienst | `~/.local/share/local-ai/whisperx_studio/desktop_service.py` |
| Auswertungslogik | `~/.local/share/local-ai/whisperx_studio/reports.py` und `report_profiles.py` |
| Sicherung des vorherigen Einstiegs und der Anleitung | `~/.local/share/local-ai/whisperx-studio-backups/electron-20261103/` |

Alle Oberflächendateien werden lokal geladen. Es gibt keinen öffentlichen Webserver und
keine externen Modellanbieter. Die Modellanfragen gehen ausschließlich an Ollama unter
`127.0.0.1:11434`. Qwen 14B kann auf der vorhandenen 8-GB-GPU teilweise auf die CPU ausweichen
und deutlich länger benötigen. Eine gemessene Qualitätsrangfolge der lokalen Modelle wird nicht behauptet.

## Tastatur und Diagnose

`Strg+O`: Audio öffnen · `Strg+S`: Projekt speichern unter · `Leertaste`: Abspielen/Pause
außerhalb von Eingaben/Schaltflächen · `Entf`: markierten Audiobereich entfernen ·
`Strg+Z`: im Audiobereich Schnitt rückgängig, im Textfeld Texteingabe rückgängig ·
`Escape`: außerhalb von Dialogen Wiedergabe stoppen und Auswahl aufheben.

**… → Aktivitätsprotokoll** zeigt Details und erlaubt eine erneute Verbindungsprüfung.

Falls der Hintergrunddienst ausfällt, **Aktivitätsprotokoll → Verbindung prüfen** wählen.
Der Dienst startet neu und öffnet das zuletzt gespeicherte Projekt. Noch offene Textkorrekturen
bleiben im Editor und werden nach erfolgreicher Wiederverbindung erneut gespeichert.
Eine zu diesem Zeitpunkt laufende Verarbeitung wird nicht automatisch fortgesetzt; den gewünschten
Auftrag erneut starten. Fertige, gültige Analyseabschnitte werden wiederverwendet.
Original-Mikrofonaufnahmen sind weiterhin im oben genannten Aufnahmeordner zu finden.

Speicherfehler werden sichtbar gemeldet. Bei fehlgeschlagenen Textänderungen bleibt der Entwurf
im Editor; der gespeicherte Projektstand wird nicht durch eine halbe Datei ersetzt.
Beschädigte oder fehlende Audio-Arbeitskopien werden beim Öffnen aus dem Original neu erzeugt.
Ungültige Projekte lassen das aktuell geöffnete Projekt bestehen. Beschädigte Analysecaches
werden neu berechnet. Auch nach einem Dienstabsturz erhalten gestartete WhisperX-/Analyseprozesse
unter Linux ein Beendigungssignal; der Audiorecorder erhält ein Stoppsignal zum Abschließen der WAV-Datei.

## Prüfung und konkrete Grenzen dieser Bearbeitung

Getestet werden Audioimport/-export, Originalschutz, Schnitt und gespeichertes Rückgängig,
Projektrückladen, Text-/Sprecheränderungen, die Einzelauswahl der Auswertungsart,
Quellenprüfung, Rücknahmen, Wiederaufnahme und die Desktop-Schnittstellen.
Zusätzlich prüfen Fehlertests fehlenden Speicherplatz, einen gescheiterten atomaren Dateiaustausch,
stille und SIGTERM ignorierende Unterprozesse, einen echten Absturz des übergeordneten Dienstes,
beschädigte Einstellungen/Projekte/Caches und verzögerte Speicherbestätigungen des Editors.
Die Prompttests mit kontrollierten Antworten sind Softwaretests, keine Messung echter Modellqualität.

Die neue sichtbare Oberfläche und echte Gemma-/Qwen-Läufe konnten in dieser
Bearbeitungssitzung nicht gestartet werden: Desktop-/Browserzugriff ist nicht verfügbar,
und der isolierte Prozessstart blockiert Chromium/Electron sowie lokale Ollama-Sockets.
Die Vorversion hatte bereits erfolgreiche echte CPU- und Live-Kern-Transkriptionstests;
die vorhandene WhisperX-Engine wird weiterverwendet. Diese Prüfungen ersetzen keinen
sichtbaren Oberflächen- oder Mikrofontest der neuen Desktopanwendung.

```sh
cd ~/.local/share/local-ai
./whisperx-venv/bin/python -m unittest -v whisperx_studio.test_core whisperx_studio.test_reports whisperx_studio.test_desktop_service whisperx_studio.test_ui
node whisperx_studio/desktop/verify.cjs
```

Stabilitätsprüfung am 03.11.2026: 73 Python-Tests und 18 JavaScript-Prüfungen bestanden.
Ruff-Prüfung, Syntaxprüfung und Desktop-Startervalidierung ebenfalls erfolgreich.
Die oben genannten Grenzen für sichtbare Oberfläche, Mikrofon und echte lokale Modellläufe bleiben bestehen.
