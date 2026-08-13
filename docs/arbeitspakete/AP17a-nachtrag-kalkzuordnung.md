# AP17a-Nachtrag — Korrekturen an der Kalk-Zuordnung

Referenz: ADR 0008 §4 und §5, AP17a, Spec §6 und §13, CLAUDE.md (Invarianten 9,
10, 11). Phase 2. Stand 13.08.2026.

Lies `geoprocessing/kalk_zuordnung.py`, `geoprocessing/stufe1_kalk.py`,
`geoprocessing/stufe2_tiles.py` und `test_kalk_zuordnung.py` vollständig, bevor
du anfängst. Dieses Paket korrigiert die fachliche Prüfung von AP17a; es baut
nichts Neues.

**Kein Nachjustieren der Kennlinie, keine neuen Faktoren.** Die
Klassenverteilung ist mit einem einzigen Faktor strukturell fast binär und wird
erst mit AP17b aussagekräftig. Wer hier an `SCHWELLE` oder `KLASSENGRENZEN`
dreht, justiert zweimal.

Das Paket läuft in drei Läufen: **A misst, B korrigiert, C validiert.** Lauf A
ändert keine Zeile Produktivcode.

---

# Lauf A — Befunde erheben (read-only)

## A1. Flächenstatistik

Innerhalb der Bbox `5.4,49.7,7.2,51.1`:

- Je Wert von `LITHOLOG_1` (IS GK 100) die Fläche in km², absteigend.
- Je Wert von `TYP_TEXT` (IS BK 50) dasselbe.
- Fläche je resultierendem Rohwert im Band **40–60** — dort, wo die Schwelle
  bei 50 tatsächlich etwas entscheidet.
- Fläche je resultierender Klasse, aktueller Stand.

CSV nach `geoprocessing/work/`, Kurzfassung in den Bericht.

Erwartungsgröße zur Gegenprobe: Nach BGR-Auswertung liegen im NRW-Anteil deiner
Bbox im Wesentlichen zwei Carbonateinheiten, Devon-Kalkstein (~911 km²
landesweit, Schwerpunkt Eifel) und Karbon-Kalkstein (~170 km², Aachener
Kohlenkalk). Weicht deine kalkgeprägte Fläche um mehr als etwa den Faktor zwei
davon ab, ist das ein Befund und gehört in den Bericht — nicht stillschweigend
hingenommen.

## A2. Drei Grep-Abfragen auf die Attributtabellen

1. **`Terra fusca`** in `TYP_TEXT` (BK 50), allein oder in zusammengesetzten
   Namen. `KALKWERT_BODENTYP` führt „Terra rossa" bei 70, aber keine Terra
   fusca. In Mitteleuropa ist Terra fusca der Kalkverwitterungslehm über Devon-
   und Massenkalk; Terra rossa ist reliktisch und hier die Ausnahme. Kommt sie
   vor und fehlt in der Tabelle, wird jede solche Fläche zu nodata — und das
   Loch läge über den Eifelkalkmulden.
2. **`Geschiebemergel`** in `LITHOLOG_1` (GK 100), und unter welchem Begriff die
   GK 100 kalkhaltiges Geschiebe sonst führt. Der Term fehlt in
   `KALKWERT_LITHOLOGIE`; landesweit ist Geschiebemergel die größte Kalkfläche
   in NRW (~2876 km²), auch wenn der Schwerpunkt nördlich der Bbox liegt.
3. **Alle Werte, die in den Daten vorkommen und in keiner der beiden Tabellen
   stehen**, mit Fläche. Das ist die Generalprobe für A1.

## A3. Rundung messen

`stufe2_tiles.py` rundet den Score auf 5 Punkte und leitet die Klasse aus dem
**gerundeten** Wert ab. Miss:

- Kachelgröße gesamt mit 5er-Rundung (Ist-Zustand).
- Kachelgröße gesamt ohne Rundung.
- Kachelgröße mit Rundung auf ganze Zahlen.

## A4. Konstanten bestätigen

`KLASSENGRENZEN` aus `gewichte.py` im Bericht ausschreiben. Die Analyse in
diesem Paket unterstellt 25 / 50 / 75. Sind sie anders gesetzt, verschieben sich
alle hier genannten Klassenangaben; der Effekt selbst bleibt.

## Lauf A ist fertig, wenn

Ein Bericht vorliegt mit: den vier Statistiken aus A1, den drei Grep-Ergebnissen
aus A2, den drei Kachelgrößen aus A3, den Klassengrenzen aus A4. Keine Änderung
an Produktivcode, kein Commit außer ggf. dem Auswertungsskript unter
`geoprocessing/work/`.

**Halt hier an und warte auf Freigabe.**

---

# Lauf B — Korrekturen

## B1. Dämpfung hinter die Kennlinie

Die eigentliche Korrektur.

`verknuepft()` wendet `DAEMPFUNG_OHNE_AUSSAGE = 0.85` auf den Rohwert an, also
**vor** `kennlinie()`. Die Kennlinie spreizt oberhalb der Schwelle mit Faktor
1,5 und staucht unterhalb mit 0,5. Belegte Folgen (aus dem Code nachgerechnet,
Werte bestätigt):

| | roh | gedämpft | Kennlinie | Klasse |
|---|---|---|---|---|
| „Kalkstein, Mergelstein" + „Braunerde" | 93,333 | 79,333 | 69,000 | 3 |
| dieselbe Fläche ohne Dämpfung | 93,333 | — | 90,000 | 4 |
| „Mergelstein, Sandstein" + „Braunerde" | 56,667 | 48,167 | 24,083 | 1 |
| dieselbe Fläche ohne Dämpfung | 56,667 | — | 35,000 | 2 |

Der zweite Fall ist ein Verstoß gegen ADR 0008 §4: Die Dämpfung schiebt eine
carbonathaltige Fläche unter die Schwelle. Das verworfene K.-o.-Kriterium kommt
durch die Hintertür wieder herein und trifft genau die Mergellinsen, die der
Verzicht schützen sollte.

Kennlinie und Dämpfung sagen Verschiedenes und dürfen sich nicht
multiplizieren. Die Kennlinie trennt carbonathaltig von nicht-carbonathaltig.
Die Dämpfung sagt „Carbonat ja, aber möglicherweise nicht im Wurzelraum". Ein
Standort verliert seine Carbonatlithologie nicht, weil eine Lössdecke
darüberliegt.

Umbau:

- `verknuepft()` liefert den **ungedämpften** Rohwert und meldet zusätzlich, ob
  der Schweige-Zweig gegriffen hat.
- Die Dämpfung wird in `kalkscore()` **nach** `kennlinie()` angewandt.
- `DAEMPFUNG_OHNE_AUSSAGE` bleibt bei 0,85 und ist damit ungefähr das, was es
  vorher zu sein vorgab. Benannte Konstante mit Begründungskommentar,
  Kalibrierliste Phase 3.
- Kommentarblöcke an `BODEN_BESTAETIGT_AB` und `DAEMPFUNG_OHNE_AUSSAGE`
  nachziehen — sie beschreiben die alte Reihenfolge.

Kette 2 landet danach bei 35,0 × 0,85 = 29,75 → Klasse 2.

## B2. Klasse vor der Rundung

99 Flächen ab Rohwert 47,5 werden derzeit auf 50 gerundet und als Klasse 3
ausgeliefert, obwohl sie unter der Schwelle liegen.

**Entscheidungsregel nach A3:** Liegt der Größenunterschied zwischen gerundeten
und ungerundeten Kacheln unter 500 KB, **streich die 5er-Rundung ganz**. Bei
7,7 MB Gesamtvolumen und 4,6 GB freiem Volume ist sie verfrühte Optimierung,
und mit sechs Teilscores in AP17b käme dieselbe Fehlerklasse sechsmal wieder.

Liegt der Unterschied darüber: Klasse aus dem ungerundeten Wert ableiten, Score
gerundet ausliefern — und den gerundeten Score so klemmen, dass er die
Klassengrenze nicht überschreitet. Sonst steht in der Aufschlüsselung Score 50
neben Klasse 2, was gegen den Geist von Invariante 10 verstößt.

## B3. Tabellen ergänzen

Nach den Befunden aus A2:

- **Terra fusca vorhanden:** Wert ergänzen, Vorschlag **85** — zwischen
  Pararendzina und Rendzina, Untergrund gesichert carbonatisch, oben meist
  entkalkt. Liegt damit über `BODEN_BESTAETIGT_AB` und wirkt bestätigend. Das
  ist beabsichtigt.
- **Terra fusca nicht vorhanden:** Zeile im Docstring, dass die Abwesenheit
  geprüft und nicht übersehen wurde. Punkt für immer erledigt.
- **Geschiebemergel bzw. dessen GK-100-Begriff vorhanden:** Wert ergänzen. Als
  kalkhaltiges Geschiebe im Bereich Mergel, Vorschlag **70**, mit Kommentar,
  dass die Entkalkungstiefe stark schwankt.
- Alle weiteren unbekannten Werte aus A2.3 mit Fläche > 1 km² ergänzen oder
  ausdrücklich als nodata begründen.

## B4. Unbekannte Werte laut melden

`litho_score` und `boden_score` liefern None bei unbekannten Werten. Richtig,
aber unsichtbar. Am Ende von Stufe 1: Liste der unbekannten Lithologie- und
Bodentypwerte mit Fläche in km², in den Log **und** in `kalk.meta.json`. Ein
künftiger GK-100-Download mit neuer Nomenklatur soll laut werden, nicht still.

## B5. Die vier Docstring-Punkte

- **Punkt 1 (Reihenfolge in `LITHOLOG_1` = Dominanz).** Der einzige mit echter
  Klassenwirkung: „Kalkstein, Tonstein" ergibt 73,3 (Klasse 3), „Tonstein,
  Kalkstein" 46,7 (Klasse 1). Prüfen in dieser Reihenfolge: (a) Legende oder
  Metadatei zum Feld `LITHOLOG_1`, (b) ob der Datensatz weitere Anteils- oder
  Prozentfelder führt. Findet sich nichts, **nicht raten** — Befund festhalten,
  Punkt offen lassen. Die Abklingfunktion `1/(i+1)` ist ebenfalls unbelegt und
  gehört im Docstring so benannt.
- **Punkt 2 (Haupttyp steht hinten).** Nach KA5-Nomenklatur steht der Grundtyp
  hinten — die Implementierung ist voraussichtlich richtig. Gegenprüfen an
  `BK50_Methoden/TYP.pdf`, dann schließen. Nebenbefund: Mit
  `HAUPTTYP_ANTEIL = 0.6` ergibt „Rendzina-Braunerde" genau 55,
  `BODEN_BESTAETIGT_AB` steht bei 60. Der häufigste Übergangstyp der
  Kalkstandorte liegt auf Messers Schneide. **Keine der beiden Zahlen ohne den
  Flächenbefund aus A1 ändern.**
- **Punkt 3 (Gips/Anhydrit bei 55): geschlossen.** Die Perm-Einheit
  (Kalkstein/Dolomitstein/Gips) liegt nach BGR-Auswertung am Ostrand von NRW bei
  Höxter, weit außerhalb der Bbox (Ostgrenze 7,2°). Kommentar an die Zeile:
  ohne Fläche im Ausschnitt, Wert unkritisch, bei Bbox-Erweiterung neu zu
  bewerten. Über A1 gegenprüfen.
- **Punkt 4 (Vulkanit bei 30): geschlossen.** Liegt unterhalb der Schwelle,
  damit klassenunwirksam. Kommentar ergänzen, schließen.

## B6. `GET /api/suitability/weights` entfernen

Der Endpunkt (AP17a §5) hat keinen Abnehmer, und das ist nicht der Hauptgrund:
Er liefert den aktiven DB-Satz, während das Frontend die tatsächlich in den
Kacheln angewandten Gewichte aus `suitability.meta.json` liest — richtigerweise,
denn nur die stehen in den Daten. Nach einer Umgewichtung ohne Pipelinelauf
liefert der Endpunkt die falsche Zahl. Ein Lese-Endpunkt, dessen Ergebnis falsch
ist, sobald jemand ihn benutzt, ist eine Falle für die nächste Instanz.

Endpunkt raus, **Tabelle und Migration bleiben** — sie sind der
Versionierungsanker. Wieder eingeführt wird er mit der Settings-Seite, die ihn
braucht.

## B7. Was ausdrücklich bleibt

- **`kalk_stufe.tif`.** Heute bitgleich mit der Nodata-Maske, ab der zweiten
  Kaskadenstufe eine eigenständige Aussage nach ADR 0008 §5. 173 KB
  rechtfertigen keinen Rückbau, den AP17b rückgängig machen muss. Gleiches
  Argument wie beim `kalk`-Attribut.
- **Das `klasse`-Attribut in den Kacheln.** Ohne es leitet der Client die Klasse
  aus dem gerundeten Score ab und bekommt dieselbe falsche Klasse — nur ohne
  erkennbare Diskrepanz. Das Attribut hat B2 überhaupt erst sichtbar gemacht.
  Es bleibt.

## B8. Tests

Ergänzen, nichts löschen oder aufweichen.

- **Regressionstest zu B1:** Eine Fläche knapp über der Schwelle bleibt mit
  nichtssagendem Bodentyp über der Schwelle. Der wichtigste neue Test.
- „Kalkstein, Mergelstein" + „Braunerde" bleibt in **Klasse 4**, nicht nur
  `>= 3`. Der bestehende Test deckelt die Dämpfung nur nach unten und hat den
  Fehler durchgelassen.
- Die Dämpfung greift nachweislich nur im Schweige-Zweig.
- **Regressionstest zu B2:** Score und Klasse in den Kacheln sind konsistent —
  kein Wert mit Score ≥ Klassengrenze und Klasse darunter.
- Falls Terra fusca ergänzt: Kalkstein + Terra fusca landet im bestätigenden
  Zweig.
- Unbekannter Wert erscheint in der Meldeliste aus B4.

## B9. Neu erzeugen

Stufe 1 und Stufe 2 lokal, Kacheln per `POST /api/suitability/upload` aufs
Volume, Layer im Planer gegenprüfen.

## Lauf B ist fertig, wenn

- `uv run pytest` grün, Lint-Gates leer, `mypy` sauber.
- Neue Kacheln auf dem Volume, Layer zeigt sie.
- **Der Bericht nennt die Klassenverteilung in km² vorher und nachher, je
  Klasse.** Ohne diese Zahl ist nicht prüfbar, was die Korrektur bewirkt hat.
- Die vier Docstring-Punkte sind geschlossen oder mit konkretem Befund neu
  formuliert. Keiner steht unverändert.

Ein Commit, Präfix `AP17a-nachtrag:`.

---

# Lauf C — Externe Validierung (read-only)

Die Forschungsgruppe Hypogäen weist für NRW über 2000 Fundstellen in vier
Großregionen aus. Zwei liegen in der Bbox:

1. **Aachener Region über Düren bis Mechernich** — Erwartung: überwiegend
   Klasse 3 und 4.
2. **Rheinauen Köln–Bonn–Remagen/Sinzig** (Düsseldorf liegt knapp nördlich der
   Bbox) — Erwartung nach aktueller Tabelle: **Klasse 1**, weil dort Carbonat im
   Lockersediment und Auenlehm liegt, nicht im Festgestein. Auenbodentypen wie
   Vega und Paternia stehen bei 30 und damit im Schweige-Band.

Vorgehen:

- Beide Regionen grob als Polygone erfassen, handdigitalisiert nach den
  Ortsnamen, bewusst ungenau. **Nur als Prüfmaske unter
  `geoprocessing/work/`, nicht als Datenlayer, nicht auf das Volume** — das sind
  fremde Daten.
- Je Region die Klassenverteilung des korrigierten Kalklayers in km².

**Befund festhalten, nicht beheben.** Ob Auenstandorte eine eigene Behandlung
brauchen, ist eine Entscheidung für AP17b, wenn der Wasserhaushaltsfaktor die
Auen ohnehin anfasst. Ergebnis als offener Punkt in **ADR 0008**, nicht als
Codekommentar — es betrifft die Faktorik, nicht die Tabelle.

Einschränkung, die in den Befund gehört: Köln und Bonn sind dicht besiedelt, ein
Fundcluster dort kann Beobachterdichte statt Habitatqualität abbilden. Für ein
echtes Habitat spricht, dass die dünn besiedelte Region Aachen–Mechernich
ebenfalls auftaucht. Aus den Meldedaten allein ist das nicht zu trennen.

---

Bei Unklarheiten anhalten und fragen, nicht raten.
