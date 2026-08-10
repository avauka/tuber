"""Gemeinsame Schema-Bausteine für die Feld-Endpunkte."""

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Zeitstempel auf UTC normalisieren.

    Die DB führt TIMESTAMPTZ in UTC, Lokalzeit ist reine Darstellung
    (CLAUDE.md). Ein naiv geliefertes Datum wird als UTC gelesen statt als
    Serverlokalzeit geraten — sonst verschiebt sich revisit_due je nachdem,
    in welcher Zeitzone der Server gerade läuft.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
