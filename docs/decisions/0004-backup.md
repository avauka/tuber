# ADR 0004 — Backup

**Datum:** 2026-08-10 · **Status:** teilweise angenommen

## Entscheidung
1. Railway Volume-Backups (täglicher Schedule) ab Tag 1 für DB- und Media-Volume.
2. Zusätzlich wöchentlicher logischer Dump (`pg_dump -Fc`) + Media-Archiv
   **off-platform**. Ziel noch offen (Kandidaten: Hetzner Storage Box,
   Backblaze B2, lokales NAS) — eigenes Arbeitspaket in Phase 1.
3. Restore-Drill einmal durchspielen, bevor Felddaten existieren.

## Nachtrag 2026-08-10 (AP9b/AP9c)
Punkt 1 ist auf dem aktuellen Railway-Plan **nicht umsetzbar**: Volume-Backups
gibt es nur im Pro-Plan. Damit ruht die gesamte Absicherung auf Punkt 2 —
**AP15 ist kein Zusatz mehr, sondern die einzige Sicherung**. Bis dahin
existiert kein Backup. Vertretbar, solange keine Felddaten erfasst sind;
ab dem ersten echten Fund nicht mehr.

Entschieden 2026-08-10: **kein Pro-Plan**, AP15 vorgezogen vor AP10/AP11.

## Begründung
Volume-Backups schützen nicht gegen Projekt-/Accountverlust (Restore nur ins
selbe Projekt; Volume löschen löscht Backups). Bei Datenhoheit-Anspruch ist ein
provider-unabhängiges Backup nicht optional.

---

## Umsetzung (AP15)

Ein Cron-Service ruft täglich `python -m app.jobs.backup_dump`. `pg_dump -Fc`
schreibt in eine Pipe, `gpg` verschlüsselt symmetrisch mit AES256. Der
Klartext berührt nie das Dateisystem — ein abgebrochener Lauf würde sonst
einen unverschlüsselten Dump mit allen Fundkoordinaten auf dem Volume
zurücklassen.

Ohne `BACKUP_PASSPHRASE` bricht der Job ab. Es gibt **keinen** Fallback auf
unverschlüsselt.

Auf dem Volume bleiben die **7 neuesten** Dumps. Das Volume ist ausdrücklich
nicht das Backup: Erst der Download über `GET /api/backups/{name}` bringt die
Kopie aus Railway heraus. `GET /api/backups` markiert deshalb jeden Stand als
`stale`, der nach sieben Tagen noch nie heruntergeladen wurde.

**Das Ziel off-platform bleibt eine Handlung, keine Automatik.** Bewusst so:
Ein automatischer Upload bräuchte ein weiteres Konto samt Zugangsdaten im
selben Container — und damit läge ein Schlüssel zum Backup genau dort, wo der
Verlust droht.

### Restore-Verfahren

Vorausgesetzt: die heruntergeladene `.dump.gpg`, die Passphrase und eine
PostgreSQL-16-Instanz mit PostGIS. Am einfachsten mit dem Projekt-Image, das
`gpg` und `pg_restore` bereits enthält.

```sh
# 1) Entschlüsseln
gpg --batch --decrypt --output tuber.dump tuber-JJJJMMTT-HHMMSS.dump.gpg

# 2) Zieldatenbank anlegen und PostGIS aktivieren
createdb tuber_restore
psql -d tuber_restore -c 'CREATE EXTENSION postgis;'

# 3) Einspielen
pg_restore --dbname=tuber_restore --no-owner --no-privileges tuber.dump

# 4) Gegenprobe
psql -d tuber_restore -c 'SELECT version_num FROM alembic_version;'
psql -d tuber_restore -c 'SELECT count(*) FROM find;'
```

Zu beachten:

- `spatial_ref_sys` ist **nicht** im Dump. Die Tabelle füllt
  `CREATE EXTENSION postgis` selbst; im Dump würde sie beim Einspielen mit
  den bereits vorhandenen Zeilen kollidieren. Eigene SRIDs gibt es nicht
  (EPSG:4326 und 25832 sind Standard).
- Der Dump enthält `alembic_version`. Nach dem Restore steht das Schema auf
  genau dem Stand des Dumps — `alembic upgrade head` bringt es bei Bedarf
  nach vorn.
- `pg_dump`/`pg_restore` im Image sind Version 17, der Server ist 16. Diese
  Richtung ist unterstützt. Zum Wiederherstellen einen Client verwenden, der
  **mindestens** so neu ist wie der, der den Dump erzeugt hat — am
  einfachsten dasselbe Image.

### Restore-Drill (Punkt 3), durchgeführt 2026-08-10

Im Container gegen die Dev-Datenbank verifiziert:

| Prüfung | Ergebnis |
|---|---|
| Lauf ohne `BACKUP_PASSPHRASE` | Exit 1, keine Datei geschrieben |
| Lauf mit Passphrase | `.dump.gpg` erzeugt, beginnt mit GPG-Paketkennung |
| Klartextprobe auf `PGDMP` | nicht auffindbar — echt verschlüsselt |
| Falsche Passphrase | Entschlüsselung abgelehnt |
| Richtige Passphrase | entschlüsselt sauber |
| `pg_restore --list` | liest das Archiv, alle 9 Tabellen + `alembic_version` |

Offen bleibt der vollständige Drill gegen eine **leere** Zieldatenbank mit
echten Felddaten. Der ist erst sinnvoll, wenn welche existieren.
