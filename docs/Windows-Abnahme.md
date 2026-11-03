# Windows-Abnahme vor einer Freigabe

Die automatisierten Tests ersetzen keine Windows-, Mikrofon-, Modell- oder GPU-Abnahme.
Diese Liste beschreibt noch auszuführende echte Systemtests, keine bereits bestandenen
Hardwaretests. **Windows nativ** ist der primäre Laufzeitpfad; Docker / WSL 2 wird separat
als Kompatibilitätsmodus geprüft.

1. Auf sauberem Windows 11 x64 Setup installieren und ohne vorinstalliertes Node.js,
   Docker Desktop oder WSL starten. Daten- und Modellordner müssen im Benutzerprofil bleiben.
2. Native CPU-Einrichtung auf einem Rechner ohne NVIDIA durchführen. Fehlt Python 3.12 x64,
   Benutzerinstallation über `winget`, erneuter Start und Reparaturpfad prüfen.
3. Ersteinrichtung mit unterbrochenem Netzwerk, abgebrochenem Paketdownload und anschließendem
   „Einrichten / reparieren“ prüfen. Eine teilweise venv darf nicht als bereit gemeldet werden.
4. NVIDIA-Automatik auf unterstützter Hardware prüfen: PyTorch und CTranslate2 müssen CUDA
   erkennen. Zusätzlich `CPU` sowie `NVIDIA-GPU erforderlich` mit absichtlich fehlendem oder
   ungeeignetem Treiber testen; CPU muss weiterhin nutzbar bleiben.
5. Whisper `small` laden, Download abbrechen und fortsetzen. Danach deutsches und englisches
   Audio nativ transkribieren und Wort-/Segmentzeitmarken prüfen.
6. Sprechertrennung separat einrichten: Hugging-Face-Read-Token, Modellfreigabe, falscher Token,
   fehlende Freigabe sowie 2- und Mehrsprecher-Aufnahmen prüfen. Normale Transkription muss auch
   ohne eingerichtete Sprechertrennung funktionieren.
7. Ollama nicht installieren und Aufnahme/Transkription vollständig prüfen. Danach Ollama nativ
   installieren, Gemma und Qwen laden, Auswertung ausführen und einen Ollama-Ausfall provozieren.
8. Mikrofon auswählen, 10 Minuten sowie 3 Stunden aufnehmen; RAM, Audioqualität, WAV-Dateikopf,
   Crash-Reparatur und Wiederöffnung prüfen.
9. AudioWorklet bei 44,1/48/96 kHz, Gerätewechsel, Entzug der Mikrofonberechtigung und
   USB-Abziehen testen. Aufnahmefehler dürfen vorhandene WAV-Daten nicht beschädigen.
10. Live-Text inklusive letztem Satz, Stoppen, Nachbearbeitung und optionale Sprechertrennung testen.
11. Audio-/Videodateien sowie Projekte über Pfade mit Leerzeichen, Umlauten und langen Dateinamen
    importieren. Die portable `/data/...`-Abbildung darf den WinWhisper-Arbeitsordner nicht verlassen.
12. Markieren, Entfernen, Zuschneiden und Rückgängig nach Projektneustart prüfen; Originaldateien
    dürfen nicht überschrieben werden.
13. Text beim schnellen Wechsel zwischen Abschnitten bearbeiten; vollen Datenträger und fehlgeschlagene
    Speicherung provozieren und prüfen, dass der neuere Entwurf erhalten bleibt.
14. Alle Auswertungsarten mit den vorgesehenen lokalen Modellen prüfen; ein langes Beispiel mit
    vielen Sprechern einbeziehen und Quellen-/Sprecherbezüge kontrollieren.
15. Nativen Python-Dienst, WhisperX-Unterprozess und Renderer jeweils gezielt beenden. Aufnahme muss
    als WAV lesbar bleiben, Projekt wiederherstellbar sein und nach Abbruch dürfen keine verwaisten
    Whisper-/CUDA-Prozesse dauerhaft weiterlaufen.
16. Markdown, Audio und Projekt nach externen Pfaden exportieren; atomaren Export, vorhandene
    Zieldateien und Schutz der importierten Originale prüfen.
17. App während Aufnahme und während eines Modelljobs schließen. Geordneter Shutdown und der
    Timeout-Fallback müssen ohne Datenverlust funktionieren.
18. App deinstallieren/neu installieren: Aufnahmen, Modellcaches, Projekte und die verwaltete
    Arbeitsumgebung müssen gemäß Produktentscheidung erhalten beziehungsweise reparierbar bleiben.
19. Nach vollständigem Caching Netzwerk trennen und DE-/EN-Transkription, bereits eingerichtete
    Diarisierung und lokale Ollama-Auswertung prüfen.
20. Erst danach den **Docker / WSL 2-Kompatibilitätsmodus** prüfen: fehlendes/gestopptes Docker,
    Linux-Container, CPU, NVIDIA-GPU, Wechsel Native→Docker→Native sowie vorhandene Arbeitsdaten.
21. Erst nach diesen Tests Setup signieren und verteilen; Zertifikat/Signierung und SmartScreen
    getrennt prüfen.

Primäre Referenzen des Entwurfs:

- Electron/NSIS: https://www.electron.build/v26/docs/nsis/
- Electron-Medienberechtigungen: https://www.electronjs.org/docs/latest/api/session
- WhisperX: https://github.com/m-bain/whisperX
- pyannote.audio: https://github.com/pyannote/pyannote-audio
- PyTorch: https://pytorch.org/get-started/locally/
- CTranslate2: https://github.com/OpenNMT/CTranslate2
- Ollama: https://github.com/ollama/ollama
- Docker unter Windows (Fallback): https://docs.docker.com/desktop/setup/install/windows-install/
- Docker/NVIDIA/WSL (Fallback): https://docs.docker.com/desktop/features/gpu/
- Inhaltliche Promptquellen: `WhisperX-Promptkonzept.md`
