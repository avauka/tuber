# Railway-Cron: Backup

Setzt ADR 0004 Punkt 2 um — und ist, da Volume-Backups den Pro-Plan
voraussetzen, **die einzige Sicherung des Projekts**.

## Warum der Cron nur anklopft

Railway kennt keine geteilten Volumes: Ein Volume gehört genau einem Service
(verifiziert 2026-08-11). Das Volume hängt am API-Service `tuber`, weil der
Download-Endpunkt es lesen muss — also muss auch der Dump dort geschrieben
werden.

Der Cron-Service schreibt deshalb nichts selbst. Er löst den Dump per HTTP im
API-Service aus und braucht dafür **weder Datenbankzugang noch ein eigenes
Volume**.

## Kommando

```
python -m app.jobs.trigger_backup
```

Eigener Cron-Service, **dasselbe Image** wie der API-Service.
Arbeitsverzeichnis `backend/`, keine Argumente.

## Umgebung

### Service `backup-cron`

| Variable | Zweck | Pflicht |
|---|---|---|
| `BASE_URL` | z. B. `https://tuber-production-9a4c.up.railway.app` | ja |
| `BACKUP_TRIGGER_TOKEN` | Bearer-Token, identisch zum API-Service | ja |

Kein `DATABASE_URL`, kein `BACKUP_PASSPHRASE`, kein Volume.

### Service `tuber` (zusätzlich zu AP9)

| Variable | Zweck | Pflicht |
|---|---|---|
| `BACKUP_DIR` | Ablage auf dem Volume, Standard `/data/backups` | ja |
| `BACKUP_PASSPHRASE` | symmetrische GPG-Passphrase | **ja** |
| `BACKUP_TRIGGER_TOKEN` | derselbe Token wie beim Cron | ja |

Volume am Service `tuber`, Mount-Pfad `/data`.

Ohne `BACKUP_PASSPHRASE` bricht der Dump ab und der Endpunkt antwortet `500`.
Es gibt keinen Fallback auf unverschlüsselt.

Ist `BACKUP_TRIGGER_TOKEN` nicht gesetzt, existiert der Token-Weg nicht: Der
Endpunkt bleibt dann per Sitzungs-Cookie erreichbar, aber der Cron kommt nicht
mehr durch. Offen wird er nie.

> Die Passphrase gehört in deinen Passwortmanager, **nicht nur** in die
> Railway-Variablen. Geht das Projekt verloren, ist sie sonst mit weg — und
> ein Dump ohne Passphrase ist Datenmüll.

## Schreibrechte auf dem Volume

Der Dienst läuft als `uid 10001`. Das Image legt `/data/backups` an und
übereignet es diesem Benutzer — beim Mounten kann Railway das aber
überdecken, dann gehört `/data` root und der Dump scheitert mit einem
Schreibfehler.

**Notausgang:** `RAILWAY_RUN_UID=0` am Service `tuber` setzen, dann läuft der
Container als root. Das gibt den Non-root-Vorteil auf und ist deshalb nur die
zweite Wahl — erst prüfen, ob es ohne geht.

## Zeitplan

Täglich, nach dem Wetter-Ingest.

## Exit-Codes des Cron-Jobs

| Code | Bedeutung |
|---|---|
| `0` | API hat den Dump geschrieben |
| `1` | `BASE_URL`/`BACKUP_TRIGGER_TOKEN` fehlt, HTTP-Fehler, oder der Dump ist gescheitert |

Ein `401` bedeutet: Token stimmt nicht überein. Ein `500` bedeutet fast immer:
`BACKUP_PASSPHRASE` fehlt am API-Service.

## Rotation

Auf dem Volume bleiben die **7 neuesten** Dumps, ältere werden beim nächsten
Lauf entfernt.

## Der eigentliche Schritt: herunterladen

Ein Dump auf dem Railway-Volume schützt nicht gegen Projekt- oder
Accountverlust — genau den Fall, für den ADR 0004 existiert. Erst die Kopie
auf einem Gerät, das Railway nicht gehört, ist ein Backup.

- `GET /api/backups` listet die Stände samt `stale`-Kennzeichnung
- `GET /api/backups/{name}` lädt einen Stand herunter (gestreamt)

`stale` bedeutet: nie heruntergeladen und älter als sieben Tage. Solange
`stale_count` grösser als null ist, liegt kein aktuelles Backup ausserhalb von
Railway.

Der Upload zu einem externen Ziel bleibt bewusst Handarbeit: Ein
automatischer Upload bräuchte Zugangsdaten für das Sicherungsziel im selben
Container — und damit läge der Schlüssel dort, wo der Verlust droht.

## Client-Hauptversion

Das Image bringt **`postgresql-client-16`** mit, passend zur Produktions-DB.
Vor jedem Dump vergleicht der Job die Hauptversion von `pg_dump` mit der des
Servers und **bricht bei Abweichung ab** (AP15.2): Ein Dump im neueren
Archivformat liesse sich mit dem passenden `pg_restore` nicht einspielen.

Wird die Datenbank je auf PostgreSQL 17 gehoben, schlägt das Backup ab dem
ersten Lauf fehl, bis die Client-Version im `backend/Dockerfile` nachgezogen
ist. Das ist Absicht.

## Lokal und für den Restore-Drill

`python -m app.jobs.backup_dump` schreibt den Dump direkt, ohne HTTP. Für den
lokalen Gebrauch und den Restore-Drill (ADR 0004) weiterhin der richtige Weg —
als Cron-Ziel auf Railway nicht mehr.

Zum Wiederherstellen auf dem eigenen Rechner: `gpg` wird gebraucht
(`winget install GnuPG.Gpg4win`) und ein `pg_restore` der Hauptversion 16.
Am einfachsten das Projekt-Image, das beides mitbringt.
