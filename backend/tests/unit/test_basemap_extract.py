"""Basiskarten-Job (ADR 0002, AP10a).

Kein Netz und kein Binary im Testlauf: `subprocess.run` ist durchgaengig
ersetzt. Geprueft wird das, was den Betrieb rettet — dass vor dem Schreiben
auf den Platz geschaut wird, dass ein abgebrochener Lauf die aktive Karte
nicht anfasst, und dass die Metadaten aus dem Archiv stammen und nicht aus
dem Dateinamen.
"""

import hashlib
import json
import os
import subprocess
from collections import namedtuple
from datetime import UTC, datetime

import pytest

from app.jobs import basemap_extract
from app.jobs.basemap_extract import BasemapError

ARCHIV = b"PMTiles-Archiv-Attrappe" * 32

# Ausschnitt einer echten Antwort von `pmtiles show --metadata`
# (build.protomaps.com/20260811.pmtiles, abgerufen 2026-08-12).
METADATEN = {
    "attribution": '<a href="https://www.openstreetmap.org/copyright">&copy; OpenStreetMap</a>',
    "name": "Protomaps Basemap",
    "planetiler:osm:osmosisreplicationtime": "2026-08-11T04:00:00Z",
    "planetiler:version": "0.10.2",
    "type": "baselayer",
    "version": "4.15.1",
    "vector_layers": [{"id": "roads", "minzoom": 3, "maxzoom": 15}],
}

_Platz = namedtuple("_Platz", "total used free")

VIEL_PLATZ = _Platz(total=5_000_000_000, used=1_000_000_000, free=4_000_000_000)


class PmtilesAttrappe:
    """Ersatz fuer `subprocess.run` — kennt genau die zwei Aufrufe des Jobs."""

    def __init__(
        self,
        *,
        inhalt: bytes = ARCHIV,
        metadaten: dict | None = None,
        extract_stderr: str | None = None,
        show_scheitert: bool = False,
        show_stdout: str | None = None,
    ) -> None:
        self.inhalt = inhalt
        self.metadaten = METADATEN if metadaten is None else metadaten
        self.extract_stderr = extract_stderr
        self.show_scheitert = show_scheitert
        self.show_stdout = show_stdout
        self.befehle: list[list[str]] = []

    def __call__(self, befehl, **kwargs):
        self.befehle.append(list(befehl))

        if befehl[1] == "extract":
            if self.extract_stderr is not None:
                raise subprocess.CalledProcessError(
                    1, befehl, output="", stderr=self.extract_stderr
                )
            # Der echte Aufruf schreibt die Zieldatei — hier dasselbe.
            with open(befehl[3], "wb") as datei:
                datei.write(self.inhalt)
            return subprocess.CompletedProcess(befehl, 0, stdout="fetching 99 chunks\n", stderr="")

        if self.show_scheitert:
            raise subprocess.CalledProcessError(
                1, befehl, output="", stderr="Failed to read pmtiles: invalid magic number\n"
            )
        ausgabe = json.dumps(self.metadaten) if self.show_stdout is None else self.show_stdout
        return subprocess.CompletedProcess(befehl, 0, stdout=ausgabe, stderr="")

    @property
    def extract_befehl(self) -> list[str]:
        return next(b for b in self.befehle if b[1] == "extract")


@pytest.fixture()
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setenv("BASEMAP_DIR", str(tmp_path))
    monkeypatch.setenv("BASEMAP_BUILD_DATE", "20260811")
    monkeypatch.delenv("BASEMAP_BBOX", raising=False)
    monkeypatch.delenv("BASEMAP_MAXZOOM", raising=False)
    # Standardfall: Platz ist da. Der Gegenfall setzt eigens zurueck.
    monkeypatch.setattr(basemap_extract.shutil, "disk_usage", lambda _pfad: VIEL_PLATZ)
    return tmp_path


@pytest.fixture()
def replace_spion(monkeypatch):
    """Haelt fest, was `os.replace` umgehaengt hat — und laesst es zu."""
    aufrufe: list[tuple[str, str]] = []
    echt = os.replace

    def _spion(quelle, ziel):
        aufrufe.append((str(quelle), str(ziel)))
        echt(quelle, ziel)

    monkeypatch.setattr(basemap_extract.os, "replace", _spion)
    return aufrufe


def _bestehende_karte(verzeichnis, inhalt: bytes = b"alte-karte") -> None:
    (verzeichnis / basemap_extract.ARCHIVE_NAME).write_bytes(inhalt)
    (verzeichnis / basemap_extract.META_NAME).write_text('{"build_date": "20260804"}')


def _tmp_dateien(verzeichnis) -> list[str]:
    return [p.name for p in verzeichnis.iterdir() if p.name.endswith(basemap_extract.TMP_SUFFIX)]


# ------------------------------------------------------------ Vorbedingungen


def test_ohne_build_datum_wird_das_binary_nicht_aufgerufen(umgebung, monkeypatch):
    """Kein geratenes "gestern": Der Build koennte noch hochladen."""
    monkeypatch.delenv("BASEMAP_BUILD_DATE")
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="BASEMAP_BUILD_DATE"):
        basemap_extract.run_extract()

    assert attrappe.befehle == []


def test_leeres_build_datum_zaehlt_als_fehlend(umgebung, monkeypatch):
    monkeypatch.setenv("BASEMAP_BUILD_DATE", "   ")
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="BASEMAP_BUILD_DATE"):
        basemap_extract.run_extract()

    assert attrappe.befehle == []


@pytest.mark.parametrize("wert", ["2026-08-11", "gestern", "202608110"])
def test_unbrauchbares_build_datum_wird_abgelehnt(umgebung, monkeypatch, wert):
    """Ein Tippfehler soll hier auffallen, nicht als 404 der Quelle."""
    monkeypatch.setenv("BASEMAP_BUILD_DATE", wert)
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="JJJJMMTT"):
        basemap_extract.run_extract()

    assert attrappe.befehle == []


def test_zu_wenig_platz_bricht_vor_dem_extract_ab(umgebung, monkeypatch):
    """Auf demselben Volume liegen die Backups (ADR 0004, AP15).

    Geprueft wird vorher: Ein Extract, der die Platte fuellt und erst danach
    auffaellt, hat die Rotation bereits gebrochen.
    """
    # 1,2 GB frei: Der Extract (300 MB erwartet) liesse weniger als 1 GB uebrig.
    knapp = _Platz(total=5_000_000_000, used=3_800_000_000, free=1_200_000_000)
    monkeypatch.setattr(basemap_extract.shutil, "disk_usage", lambda _pfad: knapp)
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="Zu wenig Platz"):
        basemap_extract.run_extract()

    assert attrappe.befehle == []
    assert list(umgebung.iterdir()) == []


def test_genug_platz_laesst_den_lauf_zu(umgebung, monkeypatch):
    """Gegenprobe zur Schwelle: 1,4 GB frei reichen fuer 300 MB."""
    reicht = _Platz(total=5_000_000_000, used=3_600_000_000, free=1_400_000_000)
    monkeypatch.setattr(basemap_extract.shutil, "disk_usage", lambda _pfad: reicht)
    monkeypatch.setattr(basemap_extract.subprocess, "run", PmtilesAttrappe())

    assert basemap_extract.run_extract().bytes == len(ARCHIV)


# ------------------------------------------------------------- Fehlerfaelle


def test_nicht_mehr_verfuegbarer_build_meldet_klartext(umgebung, monkeypatch):
    """Protomaps haelt nur die Builds der letzten Woche vor."""
    attrappe = PmtilesAttrappe(
        extract_stderr=(
            "2026/08/12 10:58:28 main.go:185: Failed to extract, Failed to create "
            "range reader for 20200101.pmtiles, HTTP error: 404\n"
        )
    )
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="nicht mehr verfuegbar"):
        basemap_extract.run_extract()


def test_abgebrochener_extract_laesst_die_karte_unveraendert(umgebung, monkeypatch):
    _bestehende_karte(umgebung)
    attrappe = PmtilesAttrappe(extract_stderr="connection reset by peer\n")
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="pmtiles extract"):
        basemap_extract.run_extract()

    assert (umgebung / basemap_extract.ARCHIVE_NAME).read_bytes() == b"alte-karte"
    assert (umgebung / basemap_extract.META_NAME).read_text() == '{"build_date": "20260804"}'
    assert _tmp_dateien(umgebung) == []


def test_unlesbares_archiv_wird_nie_zur_aktiven_karte(umgebung, monkeypatch):
    """Eine halbe Uebertragung erkennt nur, wer die Datei oeffnet.

    Die Groesse allein sagt nichts: Ein bei 90 Prozent abgebrochener Download
    ist gross genug und trotzdem unbrauchbar.
    """
    _bestehende_karte(umgebung)
    attrappe = PmtilesAttrappe(show_scheitert=True)
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="nicht lesbar"):
        basemap_extract.run_extract()

    assert (umgebung / basemap_extract.ARCHIVE_NAME).read_bytes() == b"alte-karte"
    assert _tmp_dateien(umgebung) == []


def test_unlesbare_metadaten_brechen_ab(umgebung, monkeypatch):
    monkeypatch.setattr(basemap_extract.subprocess, "run", PmtilesAttrappe(show_stdout="kein JSON"))

    with pytest.raises(BasemapError, match="kein JSON"):
        basemap_extract.run_extract()

    assert _tmp_dateien(umgebung) == []
    assert not (umgebung / basemap_extract.ARCHIVE_NAME).exists()


def test_fehlender_datenstand_bricht_ab(umgebung, monkeypatch):
    """Ohne Datenstand keine Attribution (Spec §15) — und kein stilles `null`."""
    _bestehende_karte(umgebung)
    ohne = {k: v for k, v in METADATEN.items() if k != "planetiler:osm:osmosisreplicationtime"}
    monkeypatch.setattr(basemap_extract.subprocess, "run", PmtilesAttrappe(metadaten=ohne))

    with pytest.raises(BasemapError, match="osmosisreplicationtime"):
        basemap_extract.run_extract()

    assert (umgebung / basemap_extract.ARCHIVE_NAME).read_bytes() == b"alte-karte"
    assert _tmp_dateien(umgebung) == []


def test_main_meldet_fehler_ueber_den_exit_code(umgebung, monkeypatch, capsys):
    monkeypatch.delenv("BASEMAP_BUILD_DATE")
    monkeypatch.setattr(basemap_extract.subprocess, "run", PmtilesAttrappe())

    assert basemap_extract.main() == 1
    assert "BASEMAP_BUILD_DATE" in capsys.readouterr().err


# --------------------------------------------------------------- Erfolgsfall


def test_erfolgsfall_haengt_um_und_schreibt_vollstaendige_metadaten(
    umgebung, monkeypatch, replace_spion
):
    _bestehende_karte(umgebung)
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)
    jetzt = datetime(2026, 8, 12, 9, 30, tzinfo=UTC)

    ergebnis = basemap_extract.run_extract(now=jetzt)

    karte = umgebung / basemap_extract.ARCHIVE_NAME
    assert karte.read_bytes() == ARCHIV
    assert _tmp_dateien(umgebung) == []
    assert ergebnis.path == karte
    assert ergebnis.bytes == len(ARCHIV)

    # Umgehaengt statt drueber geschrieben — auf demselben Dateisystem atomar.
    assert (str(karte) + basemap_extract.TMP_SUFFIX, str(karte)) in replace_spion

    meta = json.loads((umgebung / basemap_extract.META_NAME).read_text())
    assert meta == {
        "build_date": "20260811",
        # Aus dem Archiv, nicht aus dem Dateinamen: das ist der Datenstand,
        # der in der Attribution erscheint.
        "osm_data_timestamp": "2026-08-11T04:00:00Z",
        "tileset_version": "4.15.1",
        "bbox": [5.4, 49.7, 7.2, 51.1],
        "maxzoom": 14,
        "bytes": len(ARCHIV),
        "sha256": hashlib.sha256(ARCHIV).hexdigest(),
        "fetched_at": "2026-08-12T09:30:00Z",
    }


def test_kommando_traegt_quelle_bbox_und_maxzoom(umgebung, monkeypatch):
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    basemap_extract.run_extract()

    befehl = attrappe.extract_befehl
    assert befehl[:3] == ["pmtiles", "extract", "https://build.protomaps.com/20260811.pmtiles"]
    assert befehl[3].endswith(basemap_extract.ARCHIVE_NAME + basemap_extract.TMP_SUFFIX)
    assert "--bbox=5.4,49.7,7.2,51.1" in befehl
    assert "--maxzoom=14" in befehl
    assert "--download-threads=8" in befehl


def test_bbox_und_maxzoom_kommen_aus_der_umgebung(umgebung, monkeypatch):
    monkeypatch.setenv("BASEMAP_BBOX", "6.0,50.0,6.5,50.5")
    monkeypatch.setenv("BASEMAP_MAXZOOM", "13")
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    basemap_extract.run_extract()

    assert "--bbox=6.0,50.0,6.5,50.5" in attrappe.extract_befehl
    assert "--maxzoom=13" in attrappe.extract_befehl
    meta = json.loads((umgebung / basemap_extract.META_NAME).read_text())
    assert meta["bbox"] == [6.0, 50.0, 6.5, 50.5]
    assert meta["maxzoom"] == 13


@pytest.mark.parametrize("wert", ["6.0,50.0,6.5", "6.0;50.0;6.5;50.5", ""])
def test_unbrauchbare_bbox_wird_abgelehnt(umgebung, monkeypatch, wert):
    monkeypatch.setenv("BASEMAP_BBOX", wert)
    attrappe = PmtilesAttrappe()
    monkeypatch.setattr(basemap_extract.subprocess, "run", attrappe)

    with pytest.raises(BasemapError, match="BASEMAP_BBOX"):
        basemap_extract.run_extract()

    assert attrappe.befehle == []


def test_liegengebliebenes_tmp_stoert_den_naechsten_lauf_nicht(umgebung, monkeypatch):
    """Nach einem harten Abbruch (SIGKILL) bleibt ein .tmp liegen."""
    (umgebung / (basemap_extract.ARCHIVE_NAME + basemap_extract.TMP_SUFFIX)).write_bytes(b"halb")
    monkeypatch.setattr(basemap_extract.subprocess, "run", PmtilesAttrappe())

    basemap_extract.run_extract()

    assert (umgebung / basemap_extract.ARCHIVE_NAME).read_bytes() == ARCHIV
    assert _tmp_dateien(umgebung) == []
