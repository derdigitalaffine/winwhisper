# WhisperX Studio · Auswertungen und Promptkonzept

Stand: 03.11.2026. Promptversion: `2026-11-03.3`.

## Das konkrete Verhalten

Eine Auswertung entsteht ausschließlich auf Anforderung. Unter **Auswertungen →
Neue Auswertung** wird genau eine Art gewählt. Ein ausführliches Protokoll erzeugt
keine zusätzliche Aufgabenliste oder Zusammenfassung. Weitere Arten können danach
gesondert angefordert werden und bleiben als eigene Ergebnisse erhalten.

| Art | Inhalt | Bewusst ausgeschlossen |
|---|---|---|
| Ausführliches Protokoll | Gut formulierter Fließtext mit Themen, Argumenten, Gegenpositionen und belegtem Gesprächsstand | Zusätzliche Kurzfassung, Aufgaben- und Beschlusslisten |
| Ergebnisprotokoll | Ergebnisse, Festlegungen und offene Punkte nach Themen | Vollständige Nacherzählung, zusätzliche Aufgabenliste |
| Verlaufsprotokoll | Chronologische Entwicklung mit belegten Sprecherpositionen | Künstlicher Konsens, separate Zusatzdokumente |
| Zusammenfassung | Kompakter Überblick über die gesamte Aufnahme | Gleich lange Wiederholung aller Abschnittszusammenfassungen |
| Aufgabenliste | Konkrete Aufgaben, Zuständige bzw. angefragte Personen, Status, genannte Fristen | Ausgedachte Zuständigkeiten, unverbindliche Ideen als Zusagen |
| Beschlüsse & Abstimmungen | Tatsächlich genannte Beschlüsse, Status und Abstimmungsergebnisse | Anträge als bereits gefasste Beschlüsse, errechnete Stimmenzahlen |
| Interviewauswertung | Tatsächliche Fragen, zugehörige Antworten, Themen und Positionen | Erfundenes Frage-Antwort-Schema, unbelegte Sprecherrollen |

Einstellbar sind Modell, optionaler Modellvergleich, Detailgrad, Ausgabesprache,
Schwerpunkt, eine zusätzliche Belegprüfung und die Aufnahme der Fundstellen in
den Markdown-Export. Der Vergleich lässt beide Modelle dieselbe gewählte Art
bearbeiten. Er fordert nicht automatisch weitere Dokumenttypen an.

## Was die Recherche für diesen Entwurf bedeutet

**Bedarfsgerechte Auswertung statt Einheitszusammenfassung.** QMSum formuliert
Besprechungszusammenfassung ausdrücklich als Aufgabe, relevante Gesprächsteile
für eine konkrete Anfrage auszuwählen und zusammenzufassen. Daraus leite ich für
diese Anwendung separate Aufträge, getrennte Ausgabeverträge und einen optionalen
Schwerpunkt ab. Das ist eine Gestaltungsentscheidung; die Arbeit liefert nicht
den einen optimalen Prompt für lokale Gemma-/Qwen-Modelle.
[QMSum, NAACL 2021](https://aclanthology.org/2021.naacl-main.472/)

**Kurzüberblick und ausführliche Dokumentation erfüllen unterschiedliche Zwecke.**
Die Studie zu Meeting Recaps untersucht Highlights und eine hierarchische
Protokollansicht als ergänzende Darstellungen für verschiedene Informationsbedürfnisse.
Das stützt die Entscheidung, diese Formen auswählbar zu machen, statt jeder
Anforderung immer ein Gesamtpaket anzuhängen.
[Asthana et al., CSCW 2024 / überarbeitete Fassung 2025](https://arxiv.org/abs/2307.15793)

**Belege zuerst.** ExplainMeetSum verknüpft Zusammenfassungen mit erklärenden
Evidenzsätzen aus dem Gespräch. Für Studio wird daraus eine engere technische
Anforderung: Jedes erzeugte Element muss Originalzitate mit vorhandenen Segment-IDs
enthalten. Die Anwendung prüft deren wörtliches Vorkommen. Ein echtes Zitat beweist
allein noch nicht, dass die formulierte Schlussfolgerung stimmt; deshalb gibt es
zusätzlich die inhaltliche Belegprüfung.
[ExplainMeetSum, ACL 2023](https://aclanthology.org/2023.acl-long.731/)

**Lange Eingabe ist nicht gleich verlässliche Verarbeitung.** „Lost in the Middle“
zeigt für untersuchte Modelle und Aufgaben, dass die Position relevanter Informationen
die Nutzung langer Kontexte beeinflussen kann. Das ist keine Messung der hier
installierten Gemma-/Qwen-Versionen. Es spricht aber gegen die Annahme, ein großes
Kontextfenster allein garantiere eine vollständige Drei-Stunden-Auswertung.
[Liu et al., Lost in the Middle](https://arxiv.org/abs/2307.03172)

**Abschnitte und anschließende Gesamtverdichtung.** Die Arbeit zur aufgabenorientierten
Zusammenfassung langer Besprechungen untersucht abschnittsweise Extraktion und
rekursive Zusammenfassung. Studio verwendet eine darauf aufbauende eigene Pipeline:
Details bleiben in Protokollen erhalten; nur bei der ausdrücklich angeforderten
Zusammenfassung folgt eine hierarchische Verdichtung zum Gesamtüberblick.
[Golia und Kalita, 2023/2024](https://arxiv.org/abs/2312.17581)

**Gesprächsspezifische Schwierigkeiten.** Der Forschungsüberblick zur abstraktiven
Besprechungszusammenfassung beschreibt die besonderen Herausforderungen von
Mehrpersonengesprächen und ihrer Bewertung. Die praktische Konsequenz hier:
Sprecherzuordnung, Dissens, Bezugnahmen und die Unterscheidung von Erwähnung und
Verantwortlichkeit sind explizite Promptregeln und eigene Prüffälle.
[Rennard et al., TACL 2023](https://aclanthology.org/2023.tacl-1.49/)

## Die Pipeline

### 1. Ein Auftrag, ein passendes Schema

Jede Art hat einen eigenen Systemprompt und ein kleines JSON-Schema. Nur bei
Aufgaben werden etwa `owner`, `owner_evidence`, `due`, `due_evidence` und ein
Aufgabenstatus angefordert. Ein Protokoll muss nicht nebenbei ungenutzte
Aufgaben- oder Zusammenfassungsfelder erzeugen.

Die Faktenauswahl und die sprachliche Formulierung richten sich nach der Art.
Ausführliche Protokolle sollen vollständige, gut lesbare Absätze enthalten;
Zusammenfassungen konzentrieren sich auf relevante Kernaussagen; Beschlusslisten
unterscheiden ausdrücklich Vorschlag, Annahme, Ablehnung, Vertagung und Rücknahme.

### 2. Begrenzt große Abschnitte mit Kontext

Das Transkript wird vollständig in begrenzten Abschnitten verarbeitet. Die
Kernabschnitte haben ungefähr höchstens 3800 Zeichen und vier Minuten Abstand
zwischen dem ersten und letzten Beginn. Sehr lange Einzelbeiträge müssen geteilt
werden; Segment-IDs bleiben dabei erhalten. Das ist eine Kontextbudget-Strategie,
keine Behauptung, ein langer Redebeitrag passe vollständig in vier Minuten.

Bis zu zwei gekürzte Nachbarbeiträge vor und nach dem Kern liefern Kontext für
Antworten, Pronomen und Änderungen. Sie sollen etwa verhindern, dass eine Bitte
ohne die unmittelbar folgende Annahme ausgewertet wird. Ein Eintrag muss mindestens
ein Kernsegment belegen; reine Nachbarinhalte sollen keine zusätzlichen Einträge erzeugen.

### 3. Wörtliche und strukturelle Prüfung

Segment-IDs müssen existieren. Belegzitate müssen wörtlich im zugehörigen Text
vorkommen. Die Kategorie muss zur angeforderten Art passen. Zuständigkeit und
genannter Termin brauchen eigene Belege; ungeklärte Angaben bleiben offen.
Nicht belegte Kalenderdaten werden entfernt. Bei komplett ungültigen
Modellantworten bricht der Lauf verständlich ab, statt ein leeres Ergebnis als
erfolgreiche Sachprüfung auszugeben. Ein ausdrücklich leeres, gültiges Ergebnis
ist dagegen zulässig, zum Beispiel wenn keine konkreten Aufgaben genannt wurden.

### 4. Optionale zweite Belegprüfung

Ein zweiter Modellaufruf prüft die Entwürfe gegen die betreffenden Originalaussagen.
Jede ID muss genau einmal bestätigt oder mit Grund abgelehnt werden. Dabei werden
Negationen, Bedingungen, Sprecher, Zuständige, Fristen, Zahlen und der Unterschied
zwischen Vorschlag und Beschluss bzw. Anfrage und Zusage besonders hervorgehoben.

Diese Prüfung verwendet das für den Auftrag gewählte Modell. Sie ist keine
unabhängige menschliche Prüfung und keine Wahrheitsgarantie. Die Einstellung
ist standardmäßig aktiv und kann zugunsten der Laufzeit ausgeschaltet werden.

### 5. Gesamtüberblick und spätere Rücknahmen

Bei **Zusammenfassung** werden belegte Zwischenresultate in begrenzten Gruppen
erneut verdichtet. Die endgültige Kurzfassung soll den gesamten Zeitraum abdecken.
Ausführliche Protokolle werden dabei nicht auf die Länge einer Kurzfassung reduziert.

Bei **Aufgabenliste** werden ausdrücklich zurückgenommene Zusagen zusätzlich mit
früheren Aufgaben derselben verantwortlichen Person abgeglichen. Nur eine eindeutig
zugeordnete, zeitlich spätere Rücknahme darf eine frühere aktive Zusage ersetzen.
Ähnliche Wörter oder ein gemeinsames Projektthema reichen nicht. Bei Unklarheit
bleiben die Einträge sichtbar. Zurückgenommene Zusagen erscheinen getrennt und
erhalten kein offenes Aufgaben-Kästchen. Ihre Belege enthalten auch die zugeordnete
frühere Zusage.

### 6. Nachvollziehbare Ergebnisse und Wiederaufnahme

Ergebnisse werden mit Modell, Art, Optionen, Promptversion und einem Hash des
Promptvertrags gespeichert. Der Zwischenspeicher berücksichtigt außerdem den
Transkript-/Projektstand. Geänderte Prompts oder Optionen verwenden nicht versehentlich
die Zwischenergebnisse eines anderen Auftrags. Fertige Abschnitte bleiben bei
Abbruch erhalten. Frühere Auswertungen werden nicht stillschweigend gelöscht.

## Modellgerechte Ansprache

**Gemma 4:** Die offizielle Dokumentation beschreibt System-, Nutzer- und Modellrollen
und einen steuerbaren Thinking-Modus. Studio übergibt Rollen über Ollamas Chat-API
und fügt keine manuellen Kontrolltoken in den Gesprächsinhalt ein. Für diese
Extraktionspipeline ist Thinking deaktiviert; der kleine Arbeitsspeicherbedarf und
die begrenzte Ausgabelänge stehen im Vordergrund. Die niedrige Temperatur für
Gemma ist eine konservative Ausgangseinstellung und noch kein empirisch bestätigtes Optimum.
[Offizielle Gemma-4-Promptformatierung](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)

**Qwen3:** Die offizielle Modellkarte unterscheidet Thinking und Non-Thinking und
empfiehlt für Non-Thinking unter anderem Temperatur 0,7, Top-p 0,8 und Top-k 20.
Diese Werte werden für `qwen3:` übernommen. Das ist modellbezogene Herstellerempfehlung,
keine Zusicherung besserer deutscher Protokolle. Das JSON-Schema, Belegprüfungen und
ein fester Seed ergänzen die Steuerung. Ein fester Seed ist keine Garantie bitgleicher
Antworten über Hardware- und Laufzeitversionen hinweg.
[Offizielle Qwen3-14B-Modellkarte](https://huggingface.co/Qwen/Qwen3-14B)

**Ollama:** Strukturierte Ausgaben werden mit einem JSON-Schema an die lokale
Chat-API übergeben. Ein korrektes JSON-Schema begrenzt die Form der Antwort,
garantiert aber keine faktische Richtigkeit. Modellauflistung und Anfragen bleiben
auf `127.0.0.1:11434`; Cloud-Modelle sind ausgeschlossen.
[Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)

## Kontrastive Prüffälle

| Transkriptinhalt | Erwartete Unterscheidung |
|---|---|
| „Ich könnte den Bericht vielleicht übernehmen.“ | Keine verbindliche Zusage |
| „Ich übernehme die Prüfung bis Freitag.“ | Ich-Sprecher als verantwortlich; Termin im Wortlaut |
| „Anna, kannst du das prüfen?“ | Anfrage, noch keine angenommene Zusage |
| „Wir müssten das mal prüfen.“ | Keine konkret vergebene Aufgabe |
| „Ich schlage vor, den Antrag anzunehmen.“ | Kein bereits gefasster Beschluss |
| „Mit 8 Ja und 3 Nein angenommen.“ | Genau genannte Stimmen; keine Enthaltungen ergänzen |
| „Das wurde nicht beschlossen.“ | Niemals als Annahme ausweisen |
| Spätere ausdrückliche Rücknahme einer Zusage | Die alte Zusage nicht unbesehen als aktive Aufgabe führen |
| Im Transkript enthaltene Anweisung an eine KI | Als Gesprächsdaten behandeln, nicht ausführen |

Die automatisierten Regressionstests prüfen Schematrennung, Quellenprüfung,
Zuordnungsregeln, Caches, Rücknahmen und technische Verarbeitung mit kontrollierten
Testantworten. Das sind Softwaretests, keine Qualitätsmessung echter Modellantworten.

Für eine reproduzierbare Prüfung echter lokaler Antworten gibt es zusätzlich:

```sh
cd ~/.local/share/local-ai
./whisperx-venv/bin/python -m whisperx_studio.evaluate_prompts --model gemma4:e2b
```

Mit mehrfach `--model` können Modelle nacheinander geprüft werden. Die Ergebnisse
werden unter `whisperx-studio/validation/prompt-evals/` gespeichert. Diese Modellprüfung
kann insbesondere bei Qwen 14B Zeit benötigen. Sie hat in der eingeschränkten
Bearbeitungssitzung mangels Zugriff auf den lokalen Ollama-Dienst noch nicht
stattgefunden; es wird keine gemessene Überlegenheit eines Modells behauptet.

Auch sehr gute Prompts können Transkriptionsfehler oder falsche Sprecherlabels
nicht zuverlässig korrigieren. Der wirksamste praktische Ablauf bleibt daher:
Transkript prüfen, Sprecher richtig benennen, die passende Art wählen und wichtige
Beschlüsse, Abstimmungszahlen und Zuständigkeiten über die Fundstellen nachlesen.
