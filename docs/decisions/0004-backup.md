# ADR 0004 — Backup

**Datum:** 2026-08-10 · **Status:** teilweise angenommen

## Entscheidung
1. Railway Volume-Backups (täglicher Schedule) ab Tag 1 für DB- und Media-Volume.
2. Zusätzlich wöchentlicher logischer Dump (`pg_dump -Fc`) + Media-Archiv
   **off-platform**. Ziel noch offen (Kandidaten: Hetzner Storage Box,
   Backblaze B2, lokales NAS) — eigenes Arbeitspaket in Phase 1.
3. Restore-Drill einmal durchspielen, bevor Felddaten existieren.

## Begründung
Volume-Backups schützen nicht gegen Projekt-/Accountverlust (Restore nur ins
selbe Projekt; Volume löschen löscht Backups). Bei Datenhoheit-Anspruch ist ein
provider-unabhängiges Backup nicht optional.
