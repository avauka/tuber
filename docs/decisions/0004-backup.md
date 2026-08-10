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

Entscheidung offen: Pro-Plan buchen (dann gilt Punkt 1 wieder) oder AP15
vorziehen, bevor Felddaten entstehen.

## Begründung
Volume-Backups schützen nicht gegen Projekt-/Accountverlust (Restore nur ins
selbe Projekt; Volume löschen löscht Backups). Bei Datenhoheit-Anspruch ist ein
provider-unabhängiges Backup nicht optional.
