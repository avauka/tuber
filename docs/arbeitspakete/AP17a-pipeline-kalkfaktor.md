# AP17a — Pipeline-Gerüst + Kalkfaktor durchgängig

Referenz: ADR 0008, Spec §6, CLAUDE.md (Invarianten 9, 10, 11). Phase 2.
Lies ADR 0008 vollständig, bevor du anfängst.

**Bewusst ein vertikaler Schnitt, keine vollständige Pipeline.** Ein Faktor
läuft durch die gesamte Kette — von der Rohdatei bis zur eingefärbten Fläche
auf der Karte im Planer. Erst wenn diese Kette steht, kommen die übrigen fünf
Faktoren dazu (AP17b), und das ist dann Fleißarbeit statt Architektur.

Gewählt ist **Kalk / pH**: schwerster Faktor mit 30 %, und die kleinsten
Downloads aller sechs (Vektordaten, kein DGM). Damit ist die Kette früh
prüfbar, ohne dass zweistellige Gigabyte bewegt werden.

---

## 1. Zielbild dieses Pakets

Ein Nutzer öffnet den Planer, schaltet den Layer „Eignung" an und sieht über
NRW eine vierstufige Flächenfärbung, die allein aus dem Kalkfaktor stammt.
Antippen zeigt: Score, Teilfaktor Kalk, verwendete Datenstufe. Über
Rheinland-Pfalz und Wallonien ist der Layer leer — korrekt, nicht kaputt.

## 2. Verarbeitung: `geoprocessing/`

Neues Verzeichnis, wie in CLAUDE.md vorgesehen. **Läuft ausschließlich lokal,
nie auf dem Server.**

- **GDAL im Container.** Ein `geoprocessing/Dockerfile` auf Basis eines
  offiziellen GDAL-Images, gepinnt. Der Nutzer arbeitet unter Windows; eine
  native GDAL-Installation ist Bastelei und wird nicht verlangt. Aufruf über
  ein `docker run` mit gemountetem Datenverzeichnis, dokumentiert in
  `geoprocessing/README.md`.
- Verzeichnisstruktur: `raw/` (Nutzer legt Downloads ab, in `.gitignore`),
  `work/` (Zwischenstände), `out/` (fertige Tiles).
- **Nichts aus `raw/` oder `work/` darf je ins Repo oder aufs Volume.**

## 3. Stufe 1 — Faktorlayer erzeugen

Zielraster: **20 m, EPSG:25832**, Ausdehnung aus der Bbox 5.4,49.7,7.2,51.1,
auf ganze Rasterzellen ausgerichtet. Die Rastergeometrie wird **einmal zentral
definiert** und von allen Faktoren geteilt — sonst passen die Layer später
nicht zellgenau aufeinander.

Für den Kalkfaktor:

- Eingang: IS GK 100 (Lithologische Zusammensetzung) und IS BK 50 (Bodentyp),
  beide Geologischer Dienst NRW, dl-de/by-2-0.
- Regelwerk Lithologie/Bodentyp → Kalkscore 0–100, als **lesbare
  Zuordnungstabelle** in einer eigenen Datei, nicht als verstreute if-Kaskade.
  Die Tabelle ist fachlich zu prüfen und wird sich ändern.
- **Steile Kennlinie, kein K.o.** (ADR 0008 §4): unterhalb der Schwelle fällt
  der Score in die unterste Klasse, die Fläche bleibt aber vorhanden.
- Ausgabe zwei GeoTIFFs, deckungsgleich: `kalk_score.tif` (0–100, nodata
  außerhalb der Datenlage) und `kalk_stufe.tif` (verwendete Kaskadenstufe je
  Zelle, siehe ADR 0008 §5).

In diesem Paket wird **nur Stufe 2 der Kaskade** bedient (GK 100 + BK 50,
NRW flächendeckend). FSK 5 als Stufe 1 und BFD50 als Stufe 3 kommen später —
die Kaskadenlogik wird aber schon so gebaut, dass weitere Stufen nur ergänzt
werden.

## 4. Stufe 2 — gewichten und Tiles schreiben

- Liest die vorhandenen Faktorlayer, gewichtet sie, legt fehlende Gewichte
  proportional auf die vorhandenen um (ADR 0008 §5). Bei nur einem Faktor
  bedeutet das: Kalk trägt 100 %. Das ist korrekt und muss so im UI erklärt
  werden.
- Vier diskrete Klassen, **kein Farbverlauf** (Spec §6).
- Ausgabe als PMTiles nach `out/suitability.pmtiles`, dazu
  `suitability.meta.json` mit: Gewichtssatz-Version, beteiligte Faktoren,
  Rasterweite, Bbox, Quellen mit Abrufdatum, `generated_at`, sha256.
- Stufe 2 muss **ohne Stufe 1 wiederholbar** sein. Das ist der Kern von
  ADR 0008 §7.

## 5. Gewichte in der Datenbank

- Tabelle für Gewichtssätze: Version, Zeitstempel, Faktor→Gewicht, aktiv-Flag.
  Alembic-Migration. Startsatz aus ADR 0008 §3 als Version 1.
- `GET /api/suitability/weights` liefert den aktiven Satz.
- **Kein Schreib-Endpunkt in diesem Paket.** Die Settings-Seite ist ein eigenes
  Paket; ein PATCH ohne UI wäre unbenutzt und ungetestet.
- `params.py` bleibt für strukturelle Konstanten. Die Gewichte gehören dort
  ausdrücklich nicht hin (ADR 0008 §7).

## 6. Ausliefern und Anzeigen

- `GET /api/suitability/tiles.pmtiles` — analog zur Basiskarte: `FileResponse`
  von `/data/suitability.pmtiles`, Range-fähig, hinter der bestehenden Auth,
  **keine Kompressions-Middleware**. Fehlt die Datei: 503 mit klarer Meldung.
- `GET /api/suitability/meta` — liefert `suitability.meta.json`.
- Der Extract-Job aus AP10a bekommt ein Geschwister-Skript, das die lokal
  erzeugte Datei auf das Volume bringt. **Weg noch offen** — beim Basemap-Paket
  wurde ein Upload-Endpunkt bewusst verworfen, hier kommt die Datei aber vom
  Rechner des Nutzers und nicht aus dem Netz. Anhalten und fragen, statt einen
  Upload-Endpunkt zu bauen.
- Im Planer: Layer „Eignung" zuschaltbar, vier Klassen, Legende. Antippen zeigt
  Score, Kalk-Teilscore und Datenstufe im Klartext (Invariante 10).
- **Sprachregelung, nicht verhandelbar** (Invariante 9): „Eignung",
  „suitability" — nie „Wahrscheinlichkeit" oder „probability", weder im UI noch
  in Variablennamen.
- Sichtbarer Hinweis am Layer: welche Faktoren enthalten sind und dass der
  Score derzeit auf einem einzigen Faktor beruht. Eine Karte, die nach sechs
  Faktoren aussieht, aber einen zeigt, wäre die schlimmste Variante.

## 7. Tests

- Rastergeometrie: identische Ausdehnung und Zellgröße über mehrere Läufe.
- Zuordnungstabelle: bekannte Lithologie-Werte → erwarteter Score, inklusive
  unbekannter Wert → nodata, nicht 0.
- Kennlinie: Wert knapp unter der Schwelle landet in der untersten Klasse, die
  Zelle bleibt aber vorhanden.
- Stufe 2: fehlender Faktor → Gewichte proportional umgelegt, Summe bleibt 100.
- Tile-Endpunkt: echter Range-Request → 206; fehlende Datei → 503.
- Keine Netzaufrufe in Tests; kleine Fixture-Raster statt echter Daten.

## 8. Was der Nutzer beschafft

Downloads von OpenGeodata.NRW, Ablage in `geoprocessing/raw/`:

- IS GK 100 (Geologische Karte 1:100.000), EPSG:25832
- IS BK 50 (Bodenkarte 1:50.000), EPSG:25832

Exakte Download-URLs, Formate und Dateigrößen sind **im Paket zu ermitteln und
im README festzuhalten** — nicht raten. Beide sind Vektordaten und deutlich
kleiner als die Rasterquellen der späteren Faktoren.

---

## Fertig, wenn

- `uv run pytest` grün, `pnpm test` grün, Lint-Gates leer, `mypy` sauber.
- Stufe 1 und Stufe 2 laufen lokal im GDAL-Container durch, aus den echten
  NRW-Daten entsteht `suitability.pmtiles`.
- Die Datei liegt auf dem Volume, der Layer erscheint im Planer, Antippen zeigt
  die Aufschlüsselung.
- `geoprocessing/README.md` beschreibt beide Stufen so, dass der Nutzer sie
  ohne Rückfrage erneut ausführen kann — mit den konkreten `docker run`-Zeilen.
- Bericht nennt: Dateigrößen der Rohdaten, Laufzeit beider Stufen, Größe der
  erzeugten Tiles, freier Platz auf `/data`.

Ein Commit, Präfix `AP17a:`. Tests dürfen ergänzt, nie gelöscht oder
aufgeweicht werden. Bei Unklarheiten anhalten und fragen, nicht raten.
