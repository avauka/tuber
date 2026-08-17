# AP-Saisonzustand — Archiv-Backfill und Anomalie

Referenz: ADR 0007 (Abschnitt „Rückweg"), Spec §5, CLAUDE.md (Test-First bei
Bedingungs-Scoring). **Phase 1.** Nummer beim Einpflegen vergeben.

## Warum

Die Bedingungs-Engine beantwortet „ist jetzt ein guter Zeitpunkt für dieses
Gebiet" über 14 Tage Rückschau. Sie kann strukturell nicht beantworten, ob
der Frühsommer ausgefallen ist — und genau das entscheidet, ob es in einem Jahr
überhaupt Fruchtkörper gibt.

Dieses Paket ergänzt eine dritte Größe neben Eignungskarte und
Bedingungs-Engine: den **Saisonzustand**. Zeithorizont sechs Monate, Aussage
„ist dieses Jahr eins".

ADR 0007 hat den Weg dafür bereits beschrieben: Archiv-Backfill als eigenes
Paket, **additiv**, in eigener Tabelle, der laufende Ingest bleibt unberührt.
Daran wird sich gehalten.

## Was ausdrücklich unverändert bleibt

- Der Wetter-Cron aus AP2/AP7. Kein zusätzlicher Parameter, kein anderer
  Endpunkt, keine geänderte Frequenz.
- `conditions_snapshot`, `rain_score` und die gesamte Bedingungs-Engine.
- Die Entscheidung aus ADR 0007, dass die Engine Modellwerte aus der
  Forecast-API nutzt. Der Saisonzustand ist eine **zweite, getrennte** Größe,
  keine Korrektur der ersten.

Wenn du beim Bauen zu dem Schluss kommst, dass sich die beiden Systeme
sinnvoll zusammenlegen ließen: **nicht tun**, sondern melden. Die Trennung ist
beabsichtigt.

## 1. Quelle und Zeitraum

`https://archive-api.open-meteo.com/v1/archive` (ERA5). Rund zwei Tage
Nachlauf, rund 25 km Auflösung — für eine Sechsmonatsbilanz unkritisch, anders
als für das 3-bis-7-Tage-Fenster der Engine.

**Prüfe die verfügbaren Parameternamen gegen die aktuelle Open-Meteo-
Dokumentation, bevor du sie verwendest.** Nicht aus der Forecast-API übernehmen
und annehmen, sie hießen dort gleich. Wenn ein gewünschter Parameter im Archiv
fehlt, melden statt ersetzen.

Einmalig je Gebiet: 180 Tage rückwirkend. Danach hält ein **monatlicher** Cron
den Zeitraum nach — nicht täglich, die Größe ändert sich langsam.

## 2. Die Normale kommt aus derselben Quelle

Der Saisonzustand ist eine **Abweichung**, keine Absolutzahl. „180 mm in sechs
Monaten" sagt nichts, „41 % des Normalwerts" sagt alles.

Die Referenz 1991–2020 wird **ebenfalls über `/v1/archive` berechnet**, für
denselben Punkt, einmalig, und in der Datenbank abgelegt. Nicht aus
DWD-Rasterwerten, obwohl die im Kartenkontext verwendet werden.

Grund: In der Differenz zweier Werte aus demselben Modell hebt sich der
Modellbias weitgehend auf. Mischt man ERA5-Ist gegen DWD-Normale, bleibt die
Differenz der Modelle als systematischer Fehler in der Anomalie stehen — und
niemand sieht ihm an, dass er kein Wettersignal ist.

Der Abruf über 30 Jahre ist der größte Einzelaufruf des Pakets. Tageswerte,
einmal je Gebiet, Ergebnis persistent. Nicht bei jedem Lauf neu holen.

## 3. Kennzahlen

Je Gebiet, jeweils als Prozent der Normale für denselben Kalenderzeitraum:

- Niederschlagssumme 30, 90 und 180 Tage.
- Mittlere Bodenfeuchte über 90 Tage, sofern das Archiv eine passende Größe
  führt (prüfen, siehe §1).

Zusätzlich absolut, ohne Normalbezug: die längste zusammenhängende
Trockenperiode in den letzten 180 Tagen.

**Keine Gesamtnote, kein einzelner Saisonscore.** Die Kennzahlen werden
einzeln angezeigt. Eine verdichtete Zahl wäre nicht kalibrierbar, solange keine
Funddaten existieren — und Invariante 10 verlangt Aufschlüsselbarkeit ohnehin.

## 4. Datenmodell

Eigene Tabelle, additiv, mit Alembic-Migration. Keine Spalte in
`conditions_snapshot`. Die Rohantwort wird analog zu `conditions_snapshot.raw`
archiviert, damit die Herkunft nachvollziehbar bleibt.

## 5. Test-First

CLAUDE.md verlangt Tests vor Code bei Bedingungs-Scoring. Das hier ist
Bedingungs-Scoring. Vor der Implementierung existieren Tests für:

- Anomalieberechnung gegen eine feste, im Test hinterlegte Normale.
- Kalenderzeitraum-Abgleich: Die 90-Tage-Summe wird gegen die Normale
  **desselben** Kalenderfensters verglichen, nicht gegen einen Jahresdurchschnitt.
- Schaltjahr am Fensterrand.
- Lückenhafte Archivantwort führt zu einem als unvollständig markierten
  Ergebnis, nicht zu einer stillen Teilsumme.
- Idempotenz: Zweimaliger Lauf für denselben Zeitraum erzeugt keine Dubletten.

## 6. Anzeige

Im Planer als Gebietsattribut, in der bestehenden Gebietsansicht. Keine neue
Seite, kein neuer Navigationspunkt. Vier Zahlen mit Bezugszeitraum und dem
Hinweis, dass es Modellwerte sind.

## Fertig, wenn

- Tests vor dem Code geschrieben und grün, Gates leer.
- Migration liegt vor, Backfill für alle bestehenden Gebiete gelaufen.
- Der monatliche Cron ist eingerichtet und dokumentiert.
- Der laufende Wetter-Cron und die Bedingungs-Engine sind nachweislich
  unverändert — Diff zeigt keine Berührung von `conditions_snapshot`,
  `rain_score` oder dem bestehenden Ingest.
- Im Bericht stehen die aktuellen Werte für mindestens ein reales Gebiet.

Ein Commit. Bei Unklarheiten anhalten und fragen, nicht raten.
