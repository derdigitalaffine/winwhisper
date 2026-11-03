# Windows-Abnahme vor einer Freigabe

Die automatisierten Tests ersetzen keine Windows-, Mikrofon- oder GPU-Abnahme.
Diese Liste beschreibt noch auszuführende echte Systemtests, keine bereits bestandenen Prüfungen.

1. Auf sauberem Windows 11 x64 Setup bauen und installieren, danach ohne Node/Python starten.
2. WSL fehlt: Aktivierung mit UAC, gegebenenfalls Neustart, erneutes Öffnen ohne Datenverlust.
3. Docker fehlt/ist gestoppt/verwendet Windows-Container: klare Diagnose, Installation/Start/Wechsel.
4. CPU-Modus ohne NVIDIA sowie NVIDIA-Modus mit aktuellem Treiber unter Docker/WSL 2 prüfen.
5. Container aus Image bauen, Resolver-Ausgabe und tatsächliche Versionen archivieren; `pip check` muss bestehen.
6. Gemma, Qwen und Whisper small laden; Download abbrechen und anschließend fortsetzen.
7. Deutsches/englisches Audio importieren, transkribieren, Wortzeitmarken und Sprecher prüfen.
8. Mikrofon auswählen, 10 Minuten sowie 3 Stunden aufnehmen; RAM, Audioqualität und Dateikopf prüfen.
9. AudioWorklet bei 44,1/48 kHz, Gerätewechsel, Entzug der Mikrofonberechtigung und USB-Abziehen testen.
10. Live-Text inklusive letztem Satz, Stoppen, Nachbearbeitung und Sprechertrennung testen.
11. Markieren, Entfernen, Zuschneiden und Rückgängig nach Projektneustart prüfen.
12. Text beim schnellen Wechsel zwischen Abschnitten bearbeiten; Fehler durch vollen Datenträger prüfen.
13. Alle sieben Auswertungsarten einzeln mit beiden Modellen prüfen; 3-Stunden-/15-Sprecher-Beispiel einbeziehen.
14. Docker-/Containerabsturz und Rendererabsturz provozieren; Aufnahme bleibt als WAV lesbar, Projekt wiederherstellbar.
15. Markdown/Audio/Projekt nach Pfaden mit Leerzeichen und Umlauten exportieren; geschützte Originale prüfen.
16. App schließen während Aufnahme und während Modelljob: sauberes Stoppen, keine fremden Container beenden.
17. App deinstallieren/neu installieren: Aufnahmen, Modellcaches und Projekte bleiben erhalten.
18. Nach vollständigem Caching Netzwerk trennen und DE-/EN-Transkription, Diarisierung und Auswertung prüfen.
19. Erst nach diesen Tests Setup signieren und verteilen; Zertifikat/Signierung und SmartScreen getrennt prüfen.

Primäre Referenzen des Entwurfs:

- Electron/NSIS: https://www.electron.build/v26/docs/nsis/
- Electron-Medienberechtigungen: https://www.electronjs.org/docs/latest/api/session
- Docker unter Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker/NVIDIA/WSL: https://docs.docker.com/desktop/features/gpu/
- WhisperX: https://github.com/m-bain/whisperX
- Ollama: https://github.com/ollama/ollama/releases/tag/v0.40.14
- Inhaltliche Promptquellen: `WhisperX-Promptkonzept.md`
