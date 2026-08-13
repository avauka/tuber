# Spec: Trüffel-Habitatkartierung & Felddokumentation

**Arbeitstitel:** TUBER (Name offen)
**Zweck:** Private, wissenschaftlich motivierte Kartierung und Dokumentation von Trüffelhabitaten und -funden im Raum Aachen/Eifel/Ardennen.
**Version:** 1.0 (Konzeptstand)

---

## 0. Abgrenzung und Grundhaltung

**Strikt getrennt von Pilzobs/OMYKO.** Eigenes Repo, eigene Datenbank, eigener Deploy. Keine gemeinsamen Tabellen, kein geteiltes Auth, kein Import/Export zwischen den Systemen. Begründung: Pilzobs ist Bio-zertifizierter Betriebsnachweis, dies hier ist private Wildkartierung. Die beiden Datenbestände dürfen sich nie berühren.

**Ehrlichkeitsprinzip.** Die App sagt nie "hier ist wahrscheinlich eine Trüffel". Sie sagt "dieser Standort erfüllt X von Y Habitatkriterien". Jede Bewertung muss aufschlüsselbar sein: welcher Faktor treibt den Score, wie gut ist die Datengrundlage an dieser Stelle. Das ist kein Höflichkeits-Disclaimer, sondern Kernanforderung an die UI.

**Datenhoheit.** Fundorte sind privat. Keine Cloud-Aggregation, kein Teilen, keine Community-Features. Single-User-System.

---

## 1. Nutzungsszenario (bindend für alle Design-Entscheidungen)

Der Ablauf hat drei getrennte Phasen mit völlig verschiedenen Anforderungen:

**A) Planung (zu Hause, Desktop/iPad, Ruhe)**
Nutzer prüft Bedingungsfenster ("lohnt sich diese Woche?"), sucht auf der Eignungskarte Zielgebiete aus, prüft Zugänglichkeit, lädt Offline-Gebiet aufs iPhone, plant Anfahrt.

**B) Feldgang (iPhone in der Jackentasche, Hund an der Leine, oft kein Netz)**
GPS loggt passiv im Hintergrund. Nutzer sucht "auf Sicht", orientiert sich am Gelände. Gelegentlicher Blick auf die Karte zur groben Orientierung. Bei Fund oder Signal: schnelles Loggen, einhändig, unter 10 Sekunden.

**C) Nachbereitung (zu Hause, gleicher Tag oder später)**
Track importieren, Funde mit Details anreichern (Art, Gewicht, Wirtsbaum, pH-Messung), Sprachnotizen auswerten, Wiederbesuch terminieren.

**Konsequenz:** Zwei UI-Modi, hart getrennt. Der Feldmodus ist kein verkleinerter Planer.

---

## 2. Phasenplan

Reihenfolge nach Verhältnis Aufwand/Nutzen. Phase 1 liefert eigenständigen Wert ohne die aufwendige Rasterberechnung.

### Phase 1 — Logger + Bedingungsfenster (MVP)
- Fundpunkte, Signalpunkte, Sprachnotizen, Fotos
- GPX-Import und Coverage-Berechnung
- Bedingungs-Engine (Wetter, Bodenfeuchte, Saison)
- Offline-Karte, Basiskartografie
- Wiederbesuchs-Erinnerungen

### Phase 2 — Eignungskarte
- Ingest-Pipeline der Geo-Layer
- Multikriterien-Scoring, Raster-Tiles
- Faktoraufschlüsselung im UI, Datenqualitäts-Ampel
- Zugänglichkeits-Layer (Schutzgebiete, Wege, Parken)

### Phase 3 — Lernkreislauf
- Fundpunkte als Trainingsdaten
- Gewichtskalibrierung, später einfaches Modell
- Saisonrückblick und Auswertung

### Backlog (später)
- Wissenschaftlicher Export (GBIF/Pilzkartierung-kompatibel)
- Capacitor-Wrapper für integriertes Hintergrund-GPS
- Weitere Regionen außerhalb NRW/Wallonie

---

## 3. Architektur

### Stack
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x + GeoAlchemy2, Alembic
- **DB:** PostgreSQL 16 + PostGIS 3.4
- **Frontend:** React 18 + Vite, TypeScript, MapLibre GL JS
- **Offline:** Service Worker (Workbox), IndexedDB für Queue und Tiles
- **Geo-Verarbeitung (offline, nicht zur Laufzeit):** GDAL/rasterio, geopandas, rio-tiler

### Warum MapLibre statt Leaflet
Vektor-Tiles, GPU-Rendering, brauchbare Offline-Story, saubere Raster-Overlays mit eigenen Farbrampen. Auf dem iPhone spürbar flüssiger.

### Tracking-Strategie (bewusste Entscheidung)
Die App loggt **nicht** selbst im Hintergrund. Hintergrund-GPS ist auf iOS für PWAs technisch nicht möglich (`watchPosition` stoppt bei ausgeschaltetem Display, kein Background Sync). Da das Gerät in der Tasche stecken soll, wird der Track von einer dedizierten GPX-Logger-App aufgezeichnet und nach dem Gang importiert.

Die App macht selbst nur **punktuelle Fixes** im Vordergrund: im Moment des Fund-Loggens, mit `getCurrentPosition({enableHighAccuracy: true})`. Das funktioniert zuverlässig, weil der Nutzer das Gerät dabei in der Hand hat.

Migrationspfad: Architektur Capacitor-ready halten (Geolocation-Zugriff hinter einem Interface kapseln, damit ein natives Plugin später ohne UI-Umbau eingehängt werden kann).

---

## 4. Datenmodell (PostGIS)

Alle Geometrien in **EPSG:4326** gespeichert, Berechnungen über `geography` oder Reprojektion auf EPSG:25832.

### `find` — Fund
```
id                  UUID PK
geom                GEOGRAPHY(Point, 4326)  NOT NULL
gps_accuracy_m      NUMERIC          -- vom Gerät gemeldet, ehrlich speichern
found_at            TIMESTAMPTZ      NOT NULL
session_id          UUID FK -> session (nullable)
species_guess       ENUM art_enum    -- siehe Abschnitt 4a; default unbestimmt
species_confidence  ENUM (sicher, wahrscheinlich, vermutung, unbestimmt)
phenotype           ENUM (sommer, burgunder, unbestimmt)  -- nur T. aestivum, siehe 4a
id_pending          BOOLEAN          -- true = Bestimmung offen, taucht in Nachbearbeitungs-Liste auf
weight_g            NUMERIC
depth_cm            NUMERIC
maturity            ENUM (unreif, reif, ueberreif, unbestimmt)
host_tree           ENUM baumart_enum
host_distance_m     NUMERIC
soil_ph_measured    NUMERIC          -- Feldmessung, überschreibt Kartenwert
calcium_reaction    ENUM (stark, schwach, keine, ungetestet)  -- HCl-Test
brule_present       BOOLEAN
truffle_fly         BOOLEAN
notes               TEXT
photo_ids           UUID[]
voice_note_ids      UUID[]
revisit_due         DATE             -- automatisch: found_at + 1 Jahr - 3 Wochen
created_at, updated_at
```

### `signal` — Signal ohne Fund
Eigene Tabelle, nicht als Flag am Fund. Diese Punkte sind für den Lernkreislauf mindestens so wertvoll wie Funde.
```
id                  UUID PK
geom                GEOGRAPHY(Point, 4326)
observed_at         TIMESTAMPTZ
session_id          UUID FK
signal_type         ENUM (hund_anzeige_ohne_fund, truffelfliege, brule_erkannt,
                          habitat_auffaellig, wirtsbaum_bestand)
dog_confidence      ENUM (stark, mittel, schwach)   -- nur bei Hundeanzeige
notes               TEXT
photo_ids           UUID[]
voice_note_ids      UUID[]
```

### `session` — Feldgang
```
id                  UUID PK
started_at          TIMESTAMPTZ
ended_at            TIMESTAMPTZ
area_label          TEXT
dog_name            TEXT
dog_work_minutes    INTEGER          -- effektive Arbeitszeit des Hundes
temperature_c       NUMERIC          -- automatisch nachgezogen
wind_kmh            NUMERIC
soil_moisture_0_7   NUMERIC          -- automatisch nachgezogen
precip_prev_7d_mm   NUMERIC
conditions_score    NUMERIC          -- Bedingungsscore zum Zeitpunkt
subjective_rating   ENUM (gut, mittel, schlecht)   -- Selbsteinschätzung Hund/Bedingungen
notes               TEXT
```

### `track` — importierter GPS-Track
```
id                  UUID PK
session_id          UUID FK
geom                GEOGRAPHY(LineString, 4326)
source              ENUM (gpx_import, native, manuell)
source_filename     TEXT
recorded_from       TIMESTAMPTZ
recorded_to         TIMESTAMPTZ
point_count         INTEGER
mean_accuracy_m     NUMERIC
length_m            NUMERIC
```

### `coverage` — abgesuchte Fläche
Aus Tracks abgeleitet, materialisiert.
```
id                  UUID PK
track_id            UUID FK
geom                GEOGRAPHY(Polygon, 4326)
buffer_m            NUMERIC          -- default 8, konfigurierbar
covered_at          DATE
confidence          ENUM (hoch, mittel, niedrig)  -- abgeleitet aus GPS-Genauigkeit
```

### `area` — geplantes/benanntes Suchgebiet
```
id                  UUID PK
name                TEXT
geom                GEOGRAPHY(Polygon, 4326)
notes               TEXT
access_notes        TEXT             -- Parken, Wege, Eigentümer
last_visited        DATE
offline_pinned      BOOLEAN
```

### `media` — Fotos und Sprachnotizen
```
id                  UUID PK
kind                ENUM (photo, voice)
storage_path        TEXT
captured_at         TIMESTAMPTZ
geom                GEOGRAPHY(Point, 4326)   -- Position bei Aufnahme
duration_s          NUMERIC          -- nur voice
transcript          TEXT             -- optional, nachträglich
processed           BOOLEAN
```

### `conditions_snapshot` — Wetterhistorie je Gebiet
```
id                  UUID PK
area_id             UUID FK
date                DATE
soil_moisture_0_7   NUMERIC
soil_moisture_7_28  NUMERIC
soil_temp_7_28      NUMERIC
precip_mm           NUMERIC
temp_mean_c         NUMERIC
raw                 JSONB
UNIQUE (area_id, date)
```

### Indizes
```sql
CREATE INDEX ON find USING GIST (geom);
CREATE INDEX ON signal USING GIST (geom);
CREATE INDEX ON coverage USING GIST (geom);
CREATE INDEX ON track USING GIST (geom);
CREATE INDEX ON area USING GIST (geom);
CREATE INDEX ON find (revisit_due) WHERE revisit_due IS NOT NULL;
```

---

## 4a. Artenkonzept

### Grundregel: Art und Saison sind getrennte Dimensionen

*Tuber aestivum* (Sommertrüffel) und *T. uncinatum* (Burgundertrüffel) sind **dieselbe Art**. Multigen-Phylogenien (Wedén et al. 2005; Molinier et al. 2013) belegen die Konspezifität; die Unterschiede in Aroma, Gleba-Farbe und Sporenornamentik sind ökologisch, nicht evolutionär bedingt. *T. uncinatum* ist heute ein Handelsname, kein gültiges Taxon.

Praktisch bleiben die beiden Formen aber unterscheidbar und relevant, weil sie **zu verschiedenen Zeiten fruktifizieren**. Deshalb:

- `species_guess` bildet die **Taxonomie** ab → *T. aestivum* ist **ein** Eintrag
- `phenotype` bildet den **Ökotyp** ab → sommer / burgunder / unbestimmt
- Die Saisonkurven der Bedingungs-Engine hängen am **Ökotyp**, nicht an der Art

Ohne diese Trennung würde der Lernkreislauf in Phase 3 Fundpunkte in zwei Gruppen splitten, die er zusammenwerfen müsste.

### `art_enum`

| Wert | Deutsch | Speisewert | Saison (grob, regional variabel) |
|---|---|---|---|
| `t_aestivum` | Sommer-/Burgundertrüffel | hoch — Hauptziel | Mai–Nov (Sommer-Ökotyp), Sep–Jan (Burgunder-Ökotyp) |
| `t_macrosporum` | Knoblauchtrüffel | hoch | Sep–Dez |
| `t_mesentericum` | Löwentrüffel | mittel, bitter-phenolisch | Herbst–Winter |
| `t_borchii` | Bianchetto / Frühlingstrüffel | mittel–hoch | Jan–Apr |
| `t_brumale` | Wintertrüffel | gering | Dez–Mär |
| `t_rufum` | Rottrüffel | ohne | ganzjährig, Schwerpunkt Sommer–Herbst |
| `t_excavatum` | Ausgehöhlte Trüffel | ohne (hart) | Sommer–Herbst |
| `t_melanosporum` | Périgordtrüffel | sehr hoch | Dez–Mär — in der Region sehr unwahrscheinlich, Fund wäre bemerkenswert |
| `tuber_spec` | Tuber, unbestimmt | — | — |
| `andere_hypogaee` | anderer Hypogäe (kein Tuber) | — | — |

### Arten ohne Speisewert sind trotzdem wertvoll

`t_rufum` und `t_excavatum` haben kulinarisch keinen Wert, sind aber **erstklassige Habitat-Indikatoren**: wo sie fruktifizieren, stimmen Kalkgehalt, Wirtsbaum und Drainage. Sie müssen daher voll loggbar sein und im Lernkreislauf als Positivsignal für Habitateignung zählen (mit eigenem, geringerem Gewicht).

**Kein Filter darf sie standardmäßig ausblenden.** In der Kartenlegende werden sie als "Indikatorarten" geführt, nicht als Beifang.

### Bestimmung ist im Feld oft nicht möglich

Sichere Ansprache braucht Geruch, Peridienstruktur, Gleba-Aderung, oft Mikroskopie der Sporen. Das UI muss aktiv zu `tuber_spec` + `id_pending = true` + Foto einladen, statt einen Rateklick zu erzwingen.

- Default beim Feld-Logging ist **`tuber_spec`, `id_pending = true`** — kein Pflichtfeld, kein Auswahldialog im Feldmodus
- Die Nachbearbeitungs-Liste zeigt alle offenen Bestimmungen
- Falsche Artlabels schaden dem Modell in Phase 3 mehr als fehlende. Das ist der Grund für die Zurückhaltung, nicht Bequemlichkeit.

### Fotoprotokoll für spätere Bestimmung
Beim Fund-Logging optional, aber empfohlen als geführte Sequenz: Fundsituation in situ → ganze Trüffel mit Maßstab → Anschnitt (Gleba-Aderung). Der dritte ist der bestimmungsrelevante.

---

## 5. Bedingungs-Engine (Phase 1, hohe Priorität)

Der wichtigste Alltagsnutzen: beantwortet "wann hingehen", nicht nur "wo".

### Datenquelle
**Open-Meteo** — kein API-Key, CC BY 4.0, kostenlos bis 10.000 Calls/Tag bei nicht-kommerzieller Nutzung. Attribution ist Pflicht und gehört sichtbar in die App.

- Forecast: `https://api.open-meteo.com/v1/forecast`
- Archiv: `https://api.open-meteo.com/v1/archive`

Relevante Variablen (hourly):
```
soil_moisture_0_to_7cm
soil_moisture_7_to_28cm
soil_temperature_7_to_28cm
precipitation
temperature_2m
wind_speed_10m
```

**Achtung:** Falsch geschriebene Variablennamen werden von der API stillschweigend ignoriert und fehlen dann in der Antwort. Der Ingest muss prüfen, ob alle angeforderten Felder zurückkamen, und sonst hart fehlschlagen.

### Scoring-Logik
Der Bedingungsscore (0–100) setzt sich aus vier Komponenten zusammen:

**1. Saisonfenster (0–30 Punkte)**
Als weiche Kurve über das Kalenderjahr, nicht als harter Schalter. Kurven hängen am **Ökotyp bzw. Zielart**, nicht an der Taxonomie (siehe 4a):

| Zielfenster | Zeitraum | Hinweis |
|---|---|---|
| Bianchetto (*t_borchii*) | Jan–Apr | Frühjahrsfenster, oft Kiefer/Hasel |
| Sommer-Ökotyp (*t_aestivum*) | Mai–Nov, Plateau Jul–Sep | Hauptfenster |
| Burgunder-Ökotyp (*t_aestivum*) | Sep–Jan, Plateau Okt–Dez | aromatisch reifer, dunklere Gleba |
| Knoblauchtrüffel (*t_macrosporum*) | Sep–Dez | |
| Löwentrüffel (*t_mesentericum*) | Herbst–Winter | |
| Wintertrüffel (*t_brumale*) | Dez–Mär | geringwertig, aber Fenster-Füller |

Alle Kurven müssen **im UI editierbar** sein — Reifezeiten schwanken regional und jährlich erheblich, und die eigenen Funddaten sind mittelfristig die bessere Quelle als jede Literaturangabe.

**Ganzjahresabdeckung ist beabsichtigt.** Die Engine gibt nie "keine Saison" zurück, sondern nennt das jeweils nächstliegende Zielfenster inklusive der dazugehörigen Wirtsbaum-Hinweise. Beispiel Februar: "Bianchetto-Fenster öffnet — Kiefer und Hasel beachten."

Der Nutzer wählt im Planer optional ein **aktives Zielfenster**; ohne Auswahl rechnet die Engine das jeweils höchstbewertete.

**2. Bodenfeuchte (0–30 Punkte)**
Optimum in der mittleren Tiefe (7–28 cm), wo die Trüffel liegt. Zu trocken = Hund riecht schlecht und Boden ist hart, zu nass = ebenfalls schlecht. Glockenkurve um einen Zielbereich.

**3. Regen-Nachlauf (0–25 Punkte)**
Der praxisrelevanteste Einzelfaktor. Ergiebiger Regen mit 3–7 Tagen Abstand ist das ideale Fenster: Boden durchfeuchtet, aber wieder begehbar, Aromen entwickelt. Berechnung aus der Niederschlagssumme der letzten 14 Tage, gewichtet nach Abstand zum heutigen Tag.

**4. Feldbedingungen für den Hund (0–15 Punkte)**
- Temperatur: zu heiß beeinträchtigt Nasenleistung und Hundewohl deutlich
- Wind: starker Wind verweht Duftfahnen
- Frost: gefrorener Boden macht die Suche sinnlos

### Ausgabe
- **7-Tage-Ausblick** je gespeichertem Gebiet, als Ampel-Balken
- **Beste-Tage-Hinweis:** "Sötenich: Mittwoch bis Freitag ideal — 22 mm Regen vor 4 Tagen, Bodenfeuchte im Optimum, 14 °C."
- Nachvollziehbarkeit: Antippen zeigt die vier Teilscores einzeln
- Optional Push-Benachrichtigung bei Score über Schwellwert (PWA-Push funktioniert ab iOS 16.4, nur bei zum Homescreen hinzugefügter App)

### Wichtig
Der Bedingungsscore wird bei jeder Session automatisch mitgespeichert (`session.conditions_score`). Ohne das kann später niemand rekonstruieren, ob ein Nullgang am Standort oder an den Bedingungen lag.

---

## 6. Eignungskarte (Phase 2)

### Prinzip
Offline vorberechnetes Raster, ausgeliefert als Vektorkacheln.
**Keine Live-Berechnung.** Zielauflösung **20 m**, EPSG:25832.
Verbindliche Detailentscheidungen: ADR 0008.

Die 20 m sind eine bewusste Vergröberung gegenüber der früheren Zielgröße von
10 m. Die schwächsten Faktoren liegen bei ~50 m (Boden) und 1 km (Klima); ein
10-m-Ergebnisraster würde eine Trennschärfe suggerieren, die drei von sechs
Faktoren nicht liefern. Die Karte beantwortet "wohin fahre ich", nicht "wo
genau im Bestand".

### Bewusste Entscheidung: eine artunabhängige Karte

Trotz der Artendifferenzierung in 4a wird **nur ein** Eignungsraster berechnet,
kein Layer je Art.

Begründung: *T. aestivum*, *macrosporum*, *mesentericum* und *brumale* teilen
Kalkbindung, Wirtsbaumspektrum und Drainageansprüche. Die Unterschiede liegen in
Feinheiten, die die Bodenkarten und der Baumarten-Layer nicht auflösen. Vier
Karten wären zu über 90 % identisch und würden eine Trennschärfe suggerieren,
die die Datengrundlage nicht hergibt.

**Wo die Arten sich real unterscheiden, ist die Zeit** — und das kostet nur eine
Saisonkurve pro Zielfenster statt eines eigenen Rasters.

Artspezifische Raster werden erst erwogen, wenn Phase 3 aus eigenen Funddaten
belastbare Unterschiede in den Faktorprofilen zeigt.

### Faktoren und Gewichte (Startwerte, kalibrierbar)

| Faktor | Gewicht | Quelle (beste Stufe) | Auflösung |
|---|---|---|---|
| Kalk/pH (abgeleitet) | 30 % | IS GK 100 Lithologie + IS FSK 5 | ~10–50 m |
| Drainage/Wasserhaushalt | 20 % | IS FSK 5 (Gesamtwasserhaushalt) | ~10 m |
| Exposition/Einstrahlung | 15 % | DGM, auf 20 m aggregiert | 20 m |
| Wirtsbaum | 15 % | Thünen Dominant Tree Species, maskiert mit der Kalamitätskarte NRW | 10 m |
| Bestandsstruktur | 10 % | nDOM50 (Geobasis NRW) | 0,5 m |
| Klima | 10 % | DWD 1-km-Raster | 1 km |

Der Wirtsbaum wiegt bewusst weniger als in früheren Fassungen (25 %): Der Layer
kennt nur die dominante Kronenbaumart, sieht die Hasel im Unterwuchs nicht und
sein Aufnahmestand liegt vor dem Fichtensterben ab 2018. Die abgegebenen 10 %
gehen an die Bestandsstruktur, die unabhängig gemessen und aktueller ist.

Die Gewichte sind zur Laufzeit änderbar und liegen versioniert in der Datenbank,
nicht im Code (ADR 0008 §7).

### Kein Ausschlusskriterium innerhalb des Scores

Weder Kalk noch Baumart wirken als K.o. Der Kalkfaktor bekommt eine steile,
nicht-lineare Kennlinie: unterhalb der Schwelle fällt der Gesamtscore in die
unterste Klasse, die Fläche bleibt aber sichtbar und der Grund aufschlüsselbar.

Begründung: Der pH-Wert ist abgeleitet, nicht gemessen (§13). Ein hartes K.o. auf
einem abgeleiteten Wert löscht Mergellinsen, Kolluvium und kleinräumige Wechsel
unwiderruflich aus der Karte — der Nutzer sähe sie nie und erführe nie, dass er
sie nicht sieht. Ein Nadelwald-Ausschluss wäre zusätzlich sachlich falsch, weil
*T. borchii* kiefernaffin ist und die Karte für die Gattung gilt.

Ein echtes K.o. gibt es nur außerhalb des Scores: Sperrflächen im
Zugänglichkeits-Layer.

### Fallback-Kaskade und Datenqualität

Je Faktor existiert eine Kaskade von der besten zur gröbsten Quelle; jede Zelle
protokolliert die verwendete Stufe. Fehlt ein Faktor vollständig, wird sein
Gewicht proportional auf die vorhandenen umgelegt und die Zelle in der Ampel
abgestuft — kein Ersatzwert, kein Auffüllen mit Mittelwerten.

Zwischen Kartenwerken wird **nicht** übersetzt: Jede Quelle bekommt eigene Regeln
auf dieselbe 0–100-Skala. Eine sichtbare Kante an der Landesgrenze ist ehrlicher
als eine geglättete Naht. Vollständige Kaskade: ADR 0008 §5.

### Räumlicher Geltungsbereich

Das Eignungsraster deckt **NRW und Rheinland-Pfalz** ab.

Für den wallonischen Teil des Kartenausschnitts gibt es **keine Eignungskarte**.
Die CNSW-Lizenz verbietet Weiterverbreitung; ein vorberechnetes Raster aus diesen
Daten wäre ein abgeleitetes Produkt und fiele unter dieselbe Beschränkung
(Invariante 12). Stattdessen wird CNSW als client-seitiges WMS-Overlay im Planer
angeboten — Textur, Drainage, Steingehalt, direkt vom wallonischen Dienst
geladen, nie über den eigenen Server.

### Datenquellen mit Endpoints

**Geologie NRW (IS GK 100)**
- Download: OpenGeodata.NRW, Shape/GeoPackage, EPSG:25832
- WMS: `https://www.wms.nrw.de/gd/wms_nw_inspire-gk100`
- Lizenz: dl-de/by-2-0, Zitierpflicht mit Abrufdatum
- Nutzung: Feld `LITHOLOG_1` der Hauptschichten (Oberflächengeologie)

**Forstliche Standortkarte NRW (IS FSK 5 / FSK 50)**
- Auswertung der BK 5 F mit Klimaatlas NRW und Reliefdaten
- Enthält Gesamtwasserhaushalt und natürliche Nährstoffversorgung direkt
- FSK 5 nur, wo eine forstliche Bodenkartierung vorliegt; FSK 50 landesweit
- Lizenz: dl-de/by-2-0

**Bodenkarte NRW (IS BK 50)**
- Download: `https://www.opengeodata.nrw.de/produkte/geologie/boden/BK/ISBK50/`
- Nutzung: Bodentyp (`TYP_TEXT`) als bestätigender/überschreibender Zeiger
- Achtung: Die Felder `ZPH_A`/`ZPH_G` sehen wie ein pH aus, sind bei 7,0 gekappt
  und trennen Rendzina kaum von Braunerde. Als Kalkzeiger unbrauchbar.
- Lizenz: dl-de/by-2-0

**Boden Rheinland-Pfalz (BFD50)**
- LGB Rheinland-Pfalz, landesweit, oberflächennaher Untergrund bis 2 m
- WMS: `mapserver.lgb-rlp.de`, INSPIRE-GML-Download
- Lizenz: dl-de/by-2-0, "©LGB-RLP (Jahr des Datenbezugs)"

**Baumarten (Thünen)**
- Layer `geonode:Dominant_Species_Class` auf atlas.thuenen.de
- 10 m, Sentinel-1/2 + Bundeswaldinventur
- Genauigkeit: 87 % bei Reinbeständen, 75,5 % gesamt
- **Zwei bekannte Blindstellen:** kartiert nur die dominante Kronenbaumart
  (Hasel im Unterwuchs unsichtbar) und ist zeitlich veraltet (§13).

**Kalamitätskarte NRW (Waldinfo.NRW / LANUV)**
- Nadelholzflächen mit starkem Vitalitätsverlust seit 2018, Flächen ab 0,1 ha
- Nutzung: Korrekturmaske über den Thünen-Layer, kein eigener Faktor
- Endet an der Landesgrenze; außerhalb NRW bleibt der Thünen-Layer unkorrigiert

**Bestandsstruktur (nDOM50, Geobasis NRW)**
- Differenz aus DGM und belaubtem bildbasiertem DOM, 50 cm Bodenauflösung
- Zwei Erfassungszyklen (DGM 5 Jahre, bDOM 4 Jahre) — Aktualität braucht immer
  zwei Zeitangaben

**Relief (DGM, Geobasis NRW)**
- DGM1 als GeoTIFF-Kacheln, offen. Die Pipeline aggregiert kachelweise auf 20 m
  und verwirft das Original sofort.

**Klima (DWD CDC)**
- Download: `https://opendata.dwd.de/climate_environment/`
- 1 km, vieljährige Mittel

**Biotop- und Schutzgebietsdaten (LANUV LINFOS)**
- Biotopkataster, FFH-Lebensraumtypen, gesetzlich geschützte Biotope
- Lizenz: dl-de/by-2-0
- **Als Overlay, nicht im Score.** Wo Kalk-Trockenrasen kartiert sind, hat
  jemand vor Ort nachgesehen — das schlägt jede Ableitung. Aber die Kartierung
  ist lückenhaft: Als Faktor im Score würde eine Erhebungslücke zum
  Standortnachteil.

**Wallonien (CNSW)**
- WMS: `https://geoservices.wallonie.be/arcgis/services/SOL_SOUS_SOL/CNSW/MapServer/WMSServer`
- **Nur client-seitig laden, nie proxyen, nie cachen** (Invariante 12)

**Fallback außerhalb der Kernregion**
- SoilGrids (ISRIC), 250 m, CC-BY

### Zugänglichkeits-Layer (nicht optional)
Ohne diesen Layer plant man Fahrten zu unerreichbaren Flächen.
- Schutzgebiete: BfN-Schutzgebietsdaten, LANUV LINFOS (NSG, FFH, Nationalpark Eifel)
- Wege und Parkmöglichkeiten: OpenStreetMap
- Truppenübungsplätze und Sperrgebiete
- Darstellung: Sperrflächen deutlich abgesetzt (Schraffur), sie überschreiben den
  Eignungs-Score visuell

### Darstellung
- **Diskrete Klassen, kein Farbverlauf.** Vier Stufen.
- **Datenqualitäts-Ampel** als eigener Layer, gespeist aus den je Zelle
  protokollierten Kaskadenstufen — keine Schätzung.
- **Faktoraufschlüsselung bei Antippen:** Teilscores plus Klartext. Solange nicht
  alle sechs Faktoren vorliegen, nennt der Layer sichtbar, welche enthalten sind
  und dass die Gewichte umgelegt wurden.

---

## 7. Frontend: zwei Modi

### Modus "Planer" (Desktop/Tablet, auch mobil aufrufbar)
- Große Karte mit umschaltbaren Layern
- Bedingungs-Dashboard: 7-Tage-Ausblick je Gebiet
- Gebietsverwaltung, Notizen zur Anfahrt
- Offline-Gebiet auswählen und herunterladen
- Fundhistorie, Filter, Auswertung
- Nachbearbeitung von Funden und Sprachnotizen
- GPX-Import

### Modus "Feld" (iPhone, einhändig)
Design-Regeln, nicht verhandelbar:
- **Vollbildkarte.** Kein Chrome, keine Navigationsleiste, kein Menü.
- **Ein großer Fund-Button** im unteren Drittel, Daumenreichweite bei einhändiger Bedienung. Mindestens 72 px Touch-Target.
- **Zweiter Button: Sprachnotiz.** Gleiche Größe, direkt daneben.
- **Dritter, kleinerer: Signal (ohne Fund).**
- Keine Dialoge, die eine zweite Hand brauchen. Ein Tap = Punkt gespeichert mit GPS, Zeit, Bedingungen. Fertig.
- Foto ist optionaler zweiter Schritt, nie blockierend.
- **Hoher Kontrast**, große Schrift, kein Dark-Mode-Standard (Sonnenlicht). Farbschema entsprechend hell und sättigungsstark.
- Safe-Area-Insets für Dynamic Island beachten.
- **GPS-Genauigkeit permanent sichtbar** als kleine Anzeige. Wenn "Genauer Standort" in iOS deaktiviert ist, liefert Safari nur 3–9 km grobe Werte — die App muss das erkennen und mit einer unübersehbaren Warnung blockieren, statt Unsinn aufzuzeichnen.
- Umschalten in den Planer-Modus nur über eine bewusste Geste, nie versehentlich.

### Feedback beim Loggen
Haptisches Feedback plus kurzer Ton bei erfolgreichem Speichern. Der Nutzer schaut nicht immer hin.

---

## 8. Offline-Strategie

**Grundannahme: iOS kann PWA-Daten jederzeit löschen. Das Gerät ist kein sicherer Speicher.**

- Jeder Fund/Signal geht sofort in eine IndexedDB-Queue und wird bei nächster Netzverbindung synchronisiert. Sync-Status pro Eintrag sichtbar.
- Ungesyncte Einträge werden im UI deutlich markiert. Ein Zähler "3 nicht synchronisiert" bleibt sichtbar, bis alles hochgeladen ist.
- Karten-Tiles für ausgewählte Gebiete vorab herunterladen. Speicherquota im Blick behalten und dem Nutzer den Verbrauch anzeigen.
- Fotos und Sprachnotizen werden komprimiert lokal gehalten und separat, verzögert hochgeladen (sie sind groß und blockieren sonst den wichtigen Metadaten-Sync).

---

## 9. GPX-Import und Coverage

### Import
- Datei-Upload (iOS Share Sheet in die PWA funktioniert)
- Parsen, Zuordnung zu einer Session über Zeitüberlappung, sonst manuell
- Duplikaterkennung über Zeitfenster und Geometrie

### Bereinigung
- Punkte mit gemeldeter Genauigkeit über Schwellwert (default 25 m) verwerfen
- Ausreißer über Geschwindigkeitsplausibilität filtern (GPS springt unter Kronendach)
- Leichte Glättung, aber Rohtrack bleibt erhalten

### Coverage-Berechnung
- Buffer um den bereinigten Track, default 8 m (effektive Suchbreite des Hundes), konfigurierbar
- `ST_Buffer` auf geography, dann Union über die Session
- Confidence-Klasse aus mittlerer GPS-Genauigkeit ableiten

### Ehrliche Grenze im UI
Bei "auf Sicht"-Suche entstehen fleckige, überlappende Tracks — keine systematische Abdeckung. Die Coverage-Karte zeigt "ungefähr hier war ich", nicht "diese Parzelle ist abgehakt". Das muss in der Legende stehen, sonst entsteht falsches Vertrauen in die Lückendarstellung.

---

## 10. Wiederbesuchs-Logik

Produktive Stellen produzieren jahrelang wieder. Dies ist der Übergang von "Notizbuch" zu "Werkzeug".

- Jeder Fund erzeugt automatisch `revisit_due` = Funddatum + 1 Jahr − 3 Wochen
- Dashboard zeigt fällige Wiederbesuche, gekoppelt an den aktuellen Bedingungsscore
- Kombinierter Hinweis: "Stelle Kall (3 Funde 2025) ist fällig, und die Bedingungen sind diese Woche gut."
- Historie je Fundort: mehrere Funde am selben Punkt werden räumlich geclustert (~15 m) und als Fundstelle mit Zeitreihe dargestellt

---

## 11. Lernkreislauf (Phase 3)

**Realistische Erwartung:** Bei einer niedrigen zweistelligen Zahl von Datenpunkten pro Saison ist das ein Mehrjahresprojekt. Kein statistisches Modell in Saison eins.

Vorgehen in Stufen:
1. **Deskriptiv (ab Saison 1):** Welche Habitat-Signaturen hatten deine Funde? Einfache Auswertung der Faktorwerte an Fundpunkten gegen den regionalen Durchschnitt.
2. **Gewichtsanpassung (ab ~30 Funden):** Manuelle oder halbautomatische Justierung der Faktorgewichte anhand der eigenen Trefferverteilung.
3. **Modell (ab ~100 Punkten inkl. Negativen):** Logistische Regression oder MaxEnt. Erst dann sinnvoll.

**Sichtbare Rückkopplung ist Pflicht.** Nach jedem Fund muss erkennbar sein, dass die App etwas dazugelernt hat — mindestens als aktualisierte Statistik. Ohne das ist Dokumentieren reine Pflichtarbeit und wird nach zwei Wochen eingestellt.

---

## 12. API-Endpunkte (Auszug)

```
POST   /api/finds                     Fund anlegen (idempotent über client_uuid)
PATCH  /api/finds/{id}                Nachbearbeitung
GET    /api/finds?bbox=&from=&to=
POST   /api/signals
POST   /api/sessions
PATCH  /api/sessions/{id}/end
POST   /api/tracks/import             GPX-Upload
GET    /api/coverage?bbox=
POST   /api/media                     Foto/Voice-Upload
GET    /api/conditions/{area_id}      7-Tage-Ausblick + Score-Aufschlüsselung
GET    /api/areas
POST   /api/areas
GET    /api/revisits/due
GET    /api/suitability/tiles.pmtiles   Eignungs-Vektorkacheln (Range-Requests)
GET    /api/suitability/meta            Gewichtssatz, Faktoren, Quellen, Stand
GET    /api/suitability/weights         aktiver Gewichtssatz
POST   /api/suitability/upload          Kacheln + Metadatei (lokal erzeugt)
GET    /api/offline/package/{area_id} Offline-Bundle (Tiles + Metadaten)
```

Sync-Endpunkt akzeptiert Batch-Uploads aus der Offline-Queue mit client-seitig generierten UUIDs, damit Wiederholungen keine Duplikate erzeugen.

---

## 13. Bekannte Grenzen (gehören ins Onboarding)

Diese Punkte sind keine Bugs, sondern Eigenschaften. Sie müssen dem Nutzer einmal klar gesagt werden:

1. Die Karte zeigt **Habitat-Eignung**, keine Fundwahrscheinlichkeit.
   Trüffelvorkommen sind auch im perfekten Habitat extrem fleckig.
2. Der pH-Wert ist aus Geologie und Bodentyp **abgeleitet**, nicht gemessen. Ein
   Feld-pH-Meter und ein HCl-Tropfen schlagen jedes Kartenpixel — deshalb gehören
   beide Messwerte ins Fundformular.
3. Der Baumarten-Layer sieht **keine Hasel im Unterwuchs**.
4. Der Baumarten-Layer ist **zeitlich veraltet**. Seit dem Dürresommer 2018 ist in
   der Eifel großflächig Fichte abgestorben und geräumt worden; wo die Karte Wald
   zeigt, steht real oft Kahlfläche. Innerhalb NRW wird das mit der
   Kalamitätskarte korrigiert, außerhalb NRW nicht.
5. Der Klimafaktor hat nur 1 km Auflösung.
6. Die Coverage zeigt ungefähre, nicht systematische Abdeckung.
7. Die **Artbestimmung im Feld ist unsicher**. "Unbestimmt" ist die richtige
   Antwort, bis Geruch, Anschnitt und ggf. Mikroskopie vorliegen.
8. Die Eignungskarte gilt **für die Gattung**, nicht für einzelne Arten.
   Artspezifisch ist nur das Zeitfenster.
9. **Für Wallonien gibt es keine Eignungskarte.** Die CNSW-Lizenz erlaubt keine
   Weiterverbreitung abgeleiteter Produkte. Dort steht nur die Basiskarte plus
   das client-seitige CNSW-Overlay zur eigenen Beurteilung.
10. Die Datengrundlage ist **nicht überall gleich gut**. Innerhalb NRW schwankt
    sie je nachdem, ob eine forstliche Bodenkartierung vorliegt; in
    Rheinland-Pfalz stammt sie aus einem anderen Kartenwerk. Die
    Datenqualitäts-Ampel zeigt das flächengenau.
11. Geologie und Bodentyp sind über Jahrzehnte stabil, der Bestandszustand nicht.
    Die Karte altert an verschiedenen Stellen verschieden schnell.

---

## 14. Rechtlicher Rahmen (Positionierung)

Die App ist ein **Kartierungs- und Dokumentationswerkzeug**. In Deutschland sind alle Arten der Gattung *Tuber* nach BArtSchV besonders geschützt; das Zugriffsverbot nach § 44 BNatSchG betrifft die Entnahme aus der freien Natur, nicht das Auffinden und Dokumentieren. Die App unterstützt daher Beobachtung, Kartierung und wissenschaftliche Dokumentation. Ein Fundformular-Feld für Entnahme existiert nicht.

---

## 15. Attribution (Pflicht, sichtbar in der App)

- Geologischer Dienst NRW (IS GK 100, IS BK 50), dl-de/by-2-0, mit Abrufdatum
- Thünen-Institut, Blickensdörfer et al. 2024, Dominant Tree Species for Germany
- DWD Climate Data Center
- Open-Meteo, CC BY 4.0
- Geobasis NRW (DGM1)
- Service public de Wallonie (CNSW) — nur client-seitig, nicht redistribuierbar
- OpenStreetMap contributors, ODbL

**Fachliche Grundlage Artenkonzept:**
- Wedén, C. et al. (2005): Species recognition in the truffle genus Tuber — the synonyms *Tuber aestivum* and *Tuber uncinatum*. Environmental Microbiology 7(10).
- Molinier, V. et al. (2013): A multigene phylogeny demonstrates that *Tuber aestivum* and *Tuber uncinatum* are conspecific. Organisms Diversity & Evolution 13, 503–512.
- Paolocci, F. et al. (2004): *Tuber aestivum* and *Tuber uncinatum*: two morphotypes or two species? FEMS Microbiology Letters 235(1), 109–115.
