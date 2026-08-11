"""Backup-Ablage und -Endpunkte (ADR 0004, AP15).

Der Dump-Lauf selbst braucht pg_dump und gpg und laeuft deshalb nur im
Container (Smoke-Test in AP15). Hier steht alles, was ohne die beiden
Programme pruefbar ist: Namenskonvention, Rotation, Pfad-Traversal,
Stale-Ableitung und das Streaming.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.jobs import backup_dump
from app.services import backups
from app.services.backups import BackupError

pytestmark = pytest.mark.db

JETZT = datetime(2026, 8, 10, 21, 0, tzinfo=UTC)


@pytest.fixture()
def backup_verzeichnis(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    return tmp_path


def _dump_anlegen(verzeichnis, moment: datetime, inhalt: bytes = b"verschluesselt") -> str:
    name = backups.build_name(moment)
    (verzeichnis / name).write_bytes(inhalt)
    return name


# ------------------------------------------------------ Namen und Rotation


def test_name_und_zeitpunkt_sind_umkehrbar(backup_verzeichnis):
    name = backups.build_name(JETZT)
    assert name == "tuber-20260810-210000.dump.gpg"
    assert backups.created_at(name) == JETZT


def test_liste_ist_neueste_zuerst_und_ignoriert_fremdes(backup_verzeichnis):
    for tage in (3, 1, 2):
        _dump_anlegen(backup_verzeichnis, JETZT - timedelta(days=tage))
    # Weder Fremddateien noch halbfertige Laeufe tauchen auf.
    (backup_verzeichnis / "notizen.txt").write_text("egal")
    (backup_verzeichnis / "tuber-20260809-120000.dump.gpg.part").write_bytes(b"halb")

    namen = [p.name for p in backups.list_backups()]

    assert len(namen) == 3
    assert namen == sorted(namen, reverse=True)


def test_rotation_behaelt_die_sieben_neuesten(backup_verzeichnis):
    for tage in range(10):
        _dump_anlegen(backup_verzeichnis, JETZT - timedelta(days=tage))

    entfernt = backups.rotate()

    assert len(entfernt) == 3
    verbleibend = backups.list_backups()
    assert len(verbleibend) == backups.KEEP_BACKUPS
    # Der aelteste verbliebene ist juenger als jeder entfernte.
    assert min(p.name for p in verbleibend) > max(entfernt)


# --------------------------------------------------------- Pfad-Traversal


@pytest.mark.parametrize(
    "boesartig",
    [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "/etc/passwd",
        "tuber-20260810-210000.dump.gpg/../../geheim",
        "....//tuber-20260810-210000.dump.gpg",
        "tuber-20260810-210000.dump.gpg.part",
        "notizen.txt",
        "",
    ],
)
def test_resolve_lehnt_unzulaessige_namen_ab(backup_verzeichnis, boesartig):
    with pytest.raises(BackupError):
        backups.resolve(boesartig)


def test_resolve_findet_echten_dump(backup_verzeichnis):
    name = _dump_anlegen(backup_verzeichnis, JETZT)
    assert backups.resolve(name).name == name


# ------------------------------------------------------------------ Stale


def test_frischer_dump_ohne_download_ist_nicht_stale(backup_verzeichnis):
    name = backups.build_name(JETZT - timedelta(days=2))
    assert backups.is_stale(name, None, JETZT) is False


def test_alter_dump_ohne_download_ist_stale(backup_verzeichnis):
    name = backups.build_name(JETZT - timedelta(days=8))
    assert backups.is_stale(name, None, JETZT) is True


def test_heruntergeladener_dump_ist_nie_stale(backup_verzeichnis):
    name = backups.build_name(JETZT - timedelta(days=30))
    assert backups.is_stale(name, JETZT - timedelta(days=29), JETZT) is False


# ----------------------------------------------------- Job ohne Passphrase


def test_ohne_passphrase_bricht_der_job_ab(backup_verzeichnis, monkeypatch):
    """Kein Fallback auf unverschluesselt, unter keinen Umstaenden."""
    monkeypatch.delenv("BACKUP_PASSPHRASE", raising=False)

    with pytest.raises(BackupError, match="BACKUP_PASSPHRASE"):
        backup_dump.run_backup()

    assert list(backup_verzeichnis.iterdir()) == []


def test_leere_passphrase_zaehlt_als_fehlend(backup_verzeichnis, monkeypatch):
    monkeypatch.setenv("BACKUP_PASSPHRASE", "   ")

    with pytest.raises(BackupError, match="BACKUP_PASSPHRASE"):
        backup_dump.run_backup()

    assert list(backup_verzeichnis.iterdir()) == []


def test_main_meldet_fehler_ueber_den_exit_code(backup_verzeichnis, monkeypatch, capsys):
    monkeypatch.delenv("BACKUP_PASSPHRASE", raising=False)

    assert backup_dump.main() == 1
    assert "BACKUP_PASSPHRASE" in capsys.readouterr().err


def test_fehlende_programme_werden_benannt(backup_verzeichnis, monkeypatch):
    monkeypatch.setenv("BACKUP_PASSPHRASE", "geheim")
    monkeypatch.setattr(backup_dump.shutil, "which", lambda _name: None)

    with pytest.raises(BackupError, match="pg_dump"):
        backup_dump.run_backup()


# -------------------------------------------------------------- Endpunkte


def test_liste_braucht_eine_sitzung(anon_client, backup_verzeichnis):
    assert anon_client.get("/api/backups").status_code == 401


def test_download_braucht_eine_sitzung(anon_client, backup_verzeichnis):
    name = _dump_anlegen(backup_verzeichnis, JETZT)
    assert anon_client.get(f"/api/backups/{name}").status_code == 401


def test_leere_liste(client, backup_verzeichnis):
    body = client.get("/api/backups").json()
    assert body["entries"] == []
    assert body["stale_count"] == 0
    assert body["keep"] == backups.KEEP_BACKUPS


def test_liste_zeigt_groesse_und_stale(client, backup_verzeichnis):
    frisch = _dump_anlegen(backup_verzeichnis, datetime.now(UTC) - timedelta(days=1), b"abc")
    alt = _dump_anlegen(backup_verzeichnis, datetime.now(UTC) - timedelta(days=9), b"abcdef")

    body = client.get("/api/backups").json()
    nach_namen = {e["name"]: e for e in body["entries"]}

    assert nach_namen[frisch]["size_bytes"] == 3
    assert nach_namen[frisch]["stale"] is False
    assert nach_namen[frisch]["downloaded_at"] is None
    assert nach_namen[alt]["size_bytes"] == 6
    assert nach_namen[alt]["stale"] is True
    assert body["stale_count"] == 1


def test_download_liefert_die_datei_und_wird_festgehalten(client, backup_verzeichnis):
    inhalt = b"\x85\x02\x0c\x03verschluesselter-inhalt"
    name = _dump_anlegen(backup_verzeichnis, datetime.now(UTC) - timedelta(days=9), inhalt)

    antwort = client.get(f"/api/backups/{name}")

    assert antwort.status_code == 200
    assert antwort.content == inhalt
    assert antwort.headers["content-type"] == "application/octet-stream"
    assert name in antwort.headers["content-disposition"]

    # Der Download ist gebucht -> der Stand gilt nicht mehr als veraltet.
    danach = client.get("/api/backups").json()
    eintrag = danach["entries"][0]
    assert eintrag["downloaded_at"] is not None
    assert eintrag["stale"] is False
    assert danach["stale_count"] == 0


def test_download_streamt_statt_alles_zu_laden(backup_verzeichnis):
    """Ein Dump kann groesser sein als der Container an RAM hat.

    Geprueft wird der Rueckgabetyp: FileResponse liest die Datei blockweise,
    waehrend etwa Response(content=pfad.read_bytes()) sie komplett in den
    Speicher holen wuerde. Ueber den TestClient waere dieser Unterschied
    nicht sichtbar — er puffert die Antwort ohnehin.
    """
    from fastapi.responses import FileResponse

    from app.api.backups import download_backup

    name = _dump_anlegen(backup_verzeichnis, JETZT, b"x" * 1024)
    antwort = download_backup(name)

    assert isinstance(antwort, FileResponse)
    assert antwort.background is not None  # Download wird erst danach gebucht


def test_grosse_datei_kommt_vollstaendig_an(client, backup_verzeichnis):
    gross = b"x" * (3 * 1024 * 1024)
    name = _dump_anlegen(backup_verzeichnis, datetime.now(UTC), gross)

    antwort = client.get(f"/api/backups/{name}")

    assert antwort.status_code == 200
    assert len(antwort.content) == len(gross)
    assert int(antwort.headers["content-length"]) == len(gross)


@pytest.mark.parametrize(
    "boesartig",
    ["..%2F..%2Fetc%2Fpasswd", "notizen.txt", "tuber-20260810-210000.dump.gpg.part"],
)
def test_download_lehnt_traversal_ab(client, backup_verzeichnis, boesartig):
    (backup_verzeichnis / "notizen.txt").write_text("geheim")
    assert client.get(f"/api/backups/{boesartig}").status_code == 404


def test_download_unbekannter_datei_ist_404(client, backup_verzeichnis):
    assert client.get("/api/backups/tuber-20200101-000000.dump.gpg").status_code == 404
