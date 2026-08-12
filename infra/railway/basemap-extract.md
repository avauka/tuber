# Basiskarte auf das Volume holen (AP10a)

Setzt ADR 0002 um: Die Basiskarte ist ein regionaler PMTiles-Extract aus dem
Protomaps-Planet-Build, der als **eine statische Datei** auf dem Volume liegt.

Ergebnis eines Laufs:

| Datei | Inhalt |
|---|---|
| `/data/basemap.pmtiles` | der Kartenausschnitt (~208 MB) |
| `/data/basemap.meta.json` | Datenstand, Tileset-Version, Bbox, Maxzoom, Grösse, sha256 |

Die Auslieferung an den Client (Endpunkt, MapLibre-Style) ist **nicht** Teil
dieses Pakets, sondern AP10b. Die Schnittstelle ist allein der Dateipfad.

## Kein Zeitplan

Der Job läuft **manuell**, nicht per Cron. Wald ändert sich langsam (ADR 0002);
ein täglicher 208-MB-Download wäre Verschwendung. Ein Lauf pro Saison genügt,
zusätzlich nach Bedarf.

Karte und Backups teilen sich bewusst dasselbe Volume: 208 MB von 5 GB sind
4 %, ein zweites Volume wäre Aufwand ohne Nutzen.

## Wo der Job läuft

Ein Railway-Volume gehört genau **einem** Service (verifiziert 2026-08-11,
siehe [`backup-cron.md`](backup-cron.md)). Das Volume hängt am Service
`tuber` — also muss der Job dort laufen, im Container des API-Service.

Ein eigener Service nach dem Muster von `backup-cron` käme an das Volume nicht
heran, und anders als beim Backup gibt es keinen HTTP-Weg, über den er
anklopfen könnte: Der Endpunkt gehört zu AP10b und existiert bewusst noch
nicht.

**Auslösung** (im laufenden Container des Service `tuber`):

```bash
railway ssh --service tuber
```

und dort:

```bash
BASEMAP_BUILD_DATE=20260812 python -m app.jobs.basemap_extract
```

Steht `railway ssh` nicht zur Verfügung, bleibt der Umweg über einen
einmaligen Deploy: Start-Kommando des Service `tuber` vorübergehend auf
`python -m app.jobs.basemap_extract` setzen, Lauf abwarten, Kommando
zurückstellen. Währenddessen ist die API nicht erreichbar — deshalb nur die
zweite Wahl.

## Umgebung

| Variable | Default | Bedeutung |
|---|---|---|
| `BASEMAP_BUILD_DATE` | **keiner — Pflicht** | Build-Datum, Form `JJJJMMTT` |
| `BASEMAP_BBOX` | `5.4,49.7,7.2,51.1` | Aachen/Eifel/Ardennen |
| `BASEMAP_MAXZOOM` | `14` | Waldwege sind ab `min_zoom 13` enthalten |
| `BASEMAP_DIR` | `/data` | Ablage, dasselbe Volume wie die Backups |

`BASEMAP_BUILD_DATE` hat **absichtlich keinen Default**. Ein geratenes
„gestern" liefe gegen einen Build, der womöglich noch hochlädt — und das Datum
verfällt ohnehin: Protomaps hält nur die Builds der letzten Woche vor. Es
gehört als Variable des einzelnen Laufs gesetzt, nicht dauerhaft an den
Service.

## Karte aktualisieren

1. Aktuelles Build-Datum auf <https://maps.protomaps.com/builds> nachsehen.
2. Job mit diesem Datum auslösen (siehe oben).
3. `basemap.meta.json` prüfen: `osm_data_timestamp` und `tileset_version`
   sollen zum neuen Build passen.

Beide Werte stammen aus den Metadaten **im Archiv**, nicht aus dem Dateinamen.
Sie sind der Datenstand, der in der Attribution erscheint (Spec §15).

Ein Lauf ist wiederholbar und in sich abgesichert: Geschrieben wird nach
`basemap.pmtiles.tmp`, umgehängt wird erst, nachdem das fertige Archiv
geöffnet werden konnte. **Scheitert irgendetwas, bleibt die bisherige Karte
unverändert liegen** — ein abgebrochener Download wird nie zur aktiven Karte.

## Platz auf dem Volume

Vor dem Download prüft der Job den freien Platz und bricht ab, wenn nach dem
Schreiben weniger als **1 GB** frei bliebe (erwarteter Bedarf konservativ
300 MB). Grund: Auf demselben Volume liegen die Backups, und die sind seit
AP15 die einzige Sicherung (ADR 0004). Ein volles Volume bricht die Rotation
still, und auffallen würde das erst beim Restore.

Der aktuelle Stand ist auch ohne Container-Zugang sichtbar: `GET /api/backups`
liefert `disk_total_bytes`, `disk_used_bytes` und `disk_free_bytes`.

## Fehlerbilder

| Meldung | Bedeutung |
|---|---|
| `BASEMAP_BUILD_DATE ist nicht gesetzt` | Variable fehlt — Datum wählen |
| `Build nicht mehr verfuegbar` | Der Build ist aus dem Fenster gefallen; neueres Datum wählen |
| `Zu wenig Platz` | Erst auf dem Volume aufräumen (alte Dumps herunterladen) |
| `Das erzeugte Archiv ist nicht lesbar` | Übertragung war unvollständig; Lauf wiederholen |

Der Job endet in jedem Fehlerfall mit Exit-Code `1` und räumt seine
`.tmp`-Datei weg.

## Schreibrechte auf dem Volume

Dieselbe Stolperstelle wie bei `/data/backups`: Der Container läuft als
`uid 10001`, ein von Railway gemountetes Volume gehört root. Dokumentierter
Zwischenstand ist `RAILWAY_RUN_UID=0` am Service `tuber` (siehe
[`backup-cron.md`](backup-cron.md)).

Scheitert der Job an einer `PermissionError`, ist das **nicht** im Job zu
reparieren — eine saubere Entrypoint-Lösung ist ein eigenes Arbeitspaket.

## go-pmtiles im Image

Das Binary kommt aus einer eigenen Build-Stage im `backend/Dockerfile`,
Version **v1.31.2**, sha256-geprüft. Es steckt im Image und wird nicht bei
jedem Lauf geholt, weil ADR 0003 es später ohnehin zur Laufzeit braucht: Die
Area-Offline-Pakete entstehen mit demselben `pmtiles extract`.

## Lokal

Derselbe Aufruf, mit eigenem Zielverzeichnis:

```bash
cd backend && BASEMAP_DIR=./data BASEMAP_BUILD_DATE=20260812 uv run python -m app.jobs.basemap_extract
```

Dafür muss `pmtiles` im PATH liegen (Release von
<https://github.com/protomaps/go-pmtiles/releases>) — im Container ist es
bereits enthalten.
