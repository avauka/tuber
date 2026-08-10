"""DATABASE_URL-Normalisierung (AP9a).

Greift für App und Alembic gleichermassen — alembic/env.py holt die URL über
dieselbe Funktion, damit Migration und Anwendung nie auseinanderlaufen.
"""

import pytest

from app.core.db import normalize_database_url

ZIEL = "postgresql+psycopg://tuber:geheim@db.railway.internal:5432/railway"


@pytest.mark.parametrize(
    "eingabe",
    [
        # Railway liefert genau das:
        "postgres://tuber:geheim@db.railway.internal:5432/railway",
        # Ohne Treiberangabe, ebenfalls verbreitet:
        "postgresql://tuber:geheim@db.railway.internal:5432/railway",
        # Bereits normalisiert: bleibt unveraendert.
        ZIEL,
    ],
)
def test_treiber_wird_ergaenzt(eingabe: str):
    assert normalize_database_url(eingabe) == ZIEL


def test_andere_treiberangabe_bleibt_unangetastet():
    """Wer bewusst einen anderen Treiber setzt, bekommt ihn auch."""
    url = "postgresql+asyncpg://tuber:geheim@localhost:5432/tuber"
    assert normalize_database_url(url) == url


def test_passwort_mit_sonderzeichen_bleibt_erhalten():
    """Nur das Schema wird ersetzt, der Rest bleibt Zeichen fuer Zeichen."""
    url = "postgres://tuber:a%2Fb%25c@localhost:5432/tuber"
    assert normalize_database_url(url) == (
        "postgresql+psycopg://tuber:a%2Fb%25c@localhost:5432/tuber"
    )


def test_nicht_postgres_url_bleibt_unangetastet():
    url = "sqlite:///lokal.db"
    assert normalize_database_url(url) == url
