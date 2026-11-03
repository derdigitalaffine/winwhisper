# Whisper-Modell in der Einrichtung

WinWhisper bietet in der Einrichtung zwei sinnvolle lokale Startmodelle an:

- **Tiny**: kleinster Download und schnellster Einstieg; gut für schwächere Rechner und zum Testen der Installation.
- **Small**: ausgewogener Standard mit besserer Transkriptionsqualität bei größerem Download.

Der Whisper-Download wird ausführlich im Einrichtungsprotokoll angezeigt. Vor einem Netzwerkzugriff prüft WinWhisper zuerst den lokalen Hugging-Face-Cache. Bei einem neuen Download werden Quelle und Cachepfad protokolliert, der Downloadfortschritt durchgereicht und danach `config.json`, `model.bin` und `tokenizer.json` geprüft. Anschließend wird der Snapshot noch einmal ausschließlich lokal auflösbar geprüft.

Schlägt der Download fehl, zeigt das Protokoll den konkreten Python-/Hugging-Face-Fehler samt Diagnosehinweis. Typische externe Ursachen sind Proxy, Firewall/Virenscanner, eine unterbrochene Verbindung oder zu wenig freier Speicherplatz. Ein erneuter Start verwendet bereits vollständig geladene Cache-Dateien weiter.
