# geoprocessing — Eignungskarte vorberechnen

Setzt ADR 0008 um. **Läuft ausschliesslich hier, nie auf dem Server.** Auf
dem Volume landet allein die fertige Kachelpyramide plus Metadatei; die
Rohdaten (mehrere hundert MB Landesdaten) berühren Railway nie.

Alles läuft im Container — **eine native GDAL-Installation unter Windows
wird nicht gebraucht**. Voraussetzung ist Docker, sonst nichts.

| Verzeichnis | Inhalt | im Repo? |
|---|---|---|
| `raw/` | heruntergeladene Landesdaten | nein (`.gitignore`) |
| `work/` | Faktorlayer und Zwischenstände | nein |
| `out/` | `suitability.pmtiles`, `suitability.meta.json` | nein |

---

## 0. Werkzeugkasten bauen

Einmal, und wieder nach jeder Änderung an `geoprocessing/`:

```bash
docker build -t tuber-geo geoprocessing/
```

Enthält GDAL 3.13.2 (gepinnt) und `go-pmtiles` v1.31.2 — dieselbe Version,
die im Backend-Image die Basiskarte ausliefert.

## 1. Rohdaten beschaffen

Beides Geologischer Dienst NRW, Lizenz **dl-de/by-2-0** (Zitierpflicht mit
Abrufdatum), EPSG:25832, offen ohne Anmeldung:

| Datensatz | Datei | Grösse | Stand |
|---|---|---|---|
| IS GK 100 (Geologische Karte 1:100.000) | `ISGK100_EPSG25832_Shape.zip` | 48,4 MB | 2020-04-22 |
| IS BK 50 (Bodenkarte 1:50.000) | `ISBK50_EPSG25832_GeoPackage.zip` | 640,8 MB | 2026-03-12 |

```bash
curl -L -o geoprocessing/raw/ISGK100_EPSG25832_Shape.zip \
  https://www.opengeodata.nrw.de/produkte/geologie/geologie/GK/ISGK100/ISGK100vektor/ISGK100_EPSG25832_Shape.zip
```

```bash
curl -L -o geoprocessing/raw/ISBK50_EPSG25832_GeoPackage.zip \
  https://www.opengeodata.nrw.de/produkte/geologie/boden/BK/ISBK50/ISBK50_EPSG25832_GeoPackage.zip
```

Entpacken — die Pfade sind fest verdrahtet, also genau so:

```bash
cd geoprocessing/raw && unzip -q ISGK100_EPSG25832_Shape.zip -d gk100_entpackt && unzip -q ISBK50_EPSG25832_GeoPackage.zip "BK50_GPKG/*" -d bk50_entpackt
```

Danach müssen diese beiden Dateien existieren:

```
geoprocessing/raw/gk100_entpackt/shape/Basismodul/GK100_Hauptschichten.shp
geoprocessing/raw/bk50_entpackt/BK50_GPKG/BK50_A.gpkg
```

Platzbedarf entpackt: rund 1,9 GB.

## 2. Stufe 1 — Faktorlayer erzeugen

**Teuer und selten.** Läuft, wenn eine Quelle neu ist. Gemessen: 18 s.

```bash
docker run --rm -v "%cd%\geoprocessing":/geo tuber-geo python3 stufe1_kalk.py
```

Unter Git Bash statt `%cd%`:

```bash
docker run --rm -v "$(pwd -W)/geoprocessing":/geo tuber-geo python3 stufe1_kalk.py
```

Ergebnis in `work/`: `kalk_score.tif` (0–100, 255 = keine Datenlage) und
`kalk_stufe.tif` (verwendete Kaskadenstufe je Zelle). Beide auf dem
gemeinsamen 20-m-Raster aus `raster.py` — **die Rastergeometrie ist einmal
zentral definiert**, sonst passen die Faktorlayer später nicht zellgenau
aufeinander.

Der Lauf schreibt ausserdem `work/kalk_stufe1.json` mit der Abdeckung und
allen Attributwerten, für die es keine Zuordnung gibt. Diese Liste gehört
angesehen: Was dort steht, bleibt als Loch in der Karte.

## 3. Stufe 2 — gewichten und Kacheln schreiben

**Billig und oft, läuft ohne Stufe 1.** Genau dafür ist die Pipeline
zweigeteilt (ADR 0008 §7): Eine Gewichtsänderung kostet Minuten, keinen Tag.
Gemessen: 208 s, überwiegend Polygonisieren.

```bash
docker run --rm -v "$(pwd -W)/geoprocessing":/geo tuber-geo python3 stufe2_tiles.py
```

Ergebnis in `out/`: `suitability.pmtiles` (7,7 MB) und
`suitability.meta.json` mit Gewichtssatz-Version, beteiligten Faktoren,
Rasterweite, Bbox, Quellen mit Abrufdatum, `generated_at` und sha256.

Fehlt ein Faktorlayer, wird sein Gewicht proportional auf die vorhandenen
umgelegt. **Solange nur der Kalkfaktor existiert, trägt er 100 %** — das
steht so in der Metadatei und wird im Planer angezeigt.

## 4. Auf das Volume bringen

Die Datei entsteht hier und kommt vom eigenen Rechner; deshalb gibt es
anders als bei der Basiskarte einen Upload-Endpunkt. Beide Dateien gehen
zusammen, damit auf dem Volume nie Kacheln ohne passende Metadatei liegen.

Erst anmelden (das Cookie landet in `kekse.txt`):

```bash
curl -s -c kekse.txt -X POST https://tuber-production-9a4c.up.railway.app/api/auth/login -H "Content-Type: application/json" -d "{\"password\":\"DEIN-PASSWORT\"}"
```

Dann hochladen:

```bash
curl -b kekse.txt -X POST https://tuber-production-9a4c.up.railway.app/api/suitability/upload -F "tiles=@geoprocessing/out/suitability.pmtiles" -F "meta=@geoprocessing/out/suitability.meta.json"
```

Der Endpunkt prüft vor dem Schreiben den freien Platz auf `/data` (dort
liegen die Backups, ADR 0004) und die PMTiles-Signatur, schreibt nach
`.tmp` und hängt erst dann um. **Scheitert etwas, bleibt die bisherige
Karte unverändert liegen.**

## 5. Tests

Ohne GDAL-Kenntnisse prüfbar, weil die Regeln reine Arithmetik sind:
Rastergeometrie, Zuordnungstabelle, Kennlinie, Gewichtsumlage.

```bash
docker run --rm tuber-geo python3 -m pytest tests -q
```

---

## Die Zuordnungstabelle ist ein Vorschlag

`kalk_zuordnung.py` ist die fachliche Mitte dieses Pakets und steht
bewusst allein: 41 Gesteinsanteile aus der GK 100, rund 50 Bodentypen aus
der BK 50, jeweils mit einem Kalkwert 0–100, dazu die Verknüpfungsregel und
die steile Kennlinie.

**Die Werte gehören geprüft und werden sich ändern.** Wer sie ändert, ändert
nur diese Datei — danach Stufe 1 und Stufe 2 erneut laufen lassen. Die
offenen fachlichen Punkte stehen oben in der Datei.

Ein Befund aus dem ersten echten Lauf steht dort ebenfalls: Über den
Eifelkalkmulden führt die BK 50 meist schlicht „Braunerde". Ein Mittelwert
beider Quellen drückte Blankenheim und Nettersheim damit in die unterste
Klasse — fachlich falsch. Der Bodentyp bestätigt oder überschreibt jetzt,
gemittelt wird nicht.

## Warum die Karte über Rheinland-Pfalz und Wallonien leer ist

Das ist richtig so, nicht kaputt.

* **Rheinland-Pfalz:** Kaskadenstufe 3 (BFD50) ist noch nicht gebaut.
* **Wallonien:** bekommt nach ADR 0008 §6 überhaupt keine Eignungskarte.
  Die CNSW-Daten dürfen nicht weiterverteilt werden (Invariante 12), und
  ein vorberechnetes Raster daraus wäre ein abgeleitetes Produkt unter
  derselben Beschränkung. Vorgesehen ist stattdessen ein client-seitiges
  WMS-Overlay — eigenes Paket.
