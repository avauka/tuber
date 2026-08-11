# Railway-Cron: Backup

Setzt ADR 0004 Punkt 2 um — und ist, da Volume-Backups den Pro-Plan
voraussetzen, **die einzige Sicherung des Projekts**.

## Kommando

```
python -m app.jobs.backup_dump
```

Zweiter Cron-Service neben `wetter-cron`, **dasselbe Image** wie der
API-Service. Arbeitsverzeichnis `backend/`, keine Argumente.

## Umgebung

| Variable | Zweck | Pflicht |
|---|---|---|
| `DATABASE_URL` | Referenz auf `PostGIS` | ja |
| `BACKUP_PASSPHRASE` | symmetrische GPG-Passphrase | **ja** |
| `BACKUP_DIR` | Ablage auf dem Volume, z. B. `/data/backups` | ja |

Ohne `BACKUP_PASSPHRASE` bricht der Job mit Exit 1 ab und schreibt nichts.
Es gibt keinen Fallback auf unverschlüsselt.

> Die Passphrase gehört in deinen Passwortmanager, **nicht nur** in die
> Railway-Variablen. Geht das Projekt verloren, ist sie sonst mit weg — und
> ein Dump ohne Passphrase ist Datenmüll.

Das Volume muss am Cron-Service **und** am API-Service hängen: Der Job
schreibt, der Download-Endpunkt liest.

## Zeitplan

Wöchentlich reicht laut ADR 0004; täglich kostet nichts und verkürzt den
möglichen Datenverlust. Empfohlen: täglich, nach dem Wetter-Ingest.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| `0` | Dump geschrieben, Rotation gelaufen |
| `1` | Passphrase fehlt, Programm fehlt, `pg_dump`/`gpg` gescheitert, Dump leer |

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
