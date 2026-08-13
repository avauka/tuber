"""Zuordnung Lithologie und Bodentyp -> Kalkscore 0-100.

**Diese Datei ist ein fachlicher Vorschlag und gehört geprüft.** Sie steht
bewusst allein und ist als Tabelle geschrieben, nicht als if-Kaskade quer
durch die Pipeline (AP17a §3). Wer die Werte ändert, ändert nur hier — und
Stufe 1 muss danach einmal neu laufen.

Grundlage
---------
*Tuber aestivum* und die übrigen Zielarten sind ausgeprägt calcicol: Sie
brauchen carbonathaltige, gut durchlüftete, basenreiche Böden, in der Regel
pH 7 aufwärts. Der Kalkfaktor trägt deshalb 30 % (ADR 0008 §3) — von allen
sechs Faktoren das meiste.

Zwei Quellen, beide Geologischer Dienst NRW, dl-de/by-2-0:

* **IS GK 100**, Layer `GK100_Hauptschichten`, Feld `LITHOLOG_1`. Das Feld
  listet die Gesteinsanteile durch Komma getrennt, der erste ist der
  vorherrschende ("Kalkstein, Mergelstein"). 115 Kombinationen aus
  41 Einzelanteilen, alle unten erfasst (Stand des Downloads 2020-04-22).
* **IS BK 50**, Layer `BK50`, Feld `TYP_TEXT` (Bodentyp im Klartext).
  136 Werte, zusammengesetzt aus rund 50 Grundtypen (Stand 2026-03-11).

Kein gemessener pH
------------------
Die Werte sind **abgeleitet**, nicht gemessen (Spec §13 Punkt 2). Deshalb
gibt es kein K.-o.-Kriterium, sondern eine steile Kennlinie (ADR 0008 §4):
Unterhalb der Schwelle fällt der Score in die unterste Klasse, die Fläche
bleibt aber sichtbar. Ein HCl-Tropfen im Feld schlägt jede Kartenaussage.

Geprüft und verworfen: die Felder `ZPH_A`/`ZPH_G` der BK 50. Sie sehen wie
ein pH aus, sind aber bei 7,0 gekappt und liegen für Rendzina (6,88) kaum
über Braunerde (6,66) — als Kalkzeiger unbrauchbar.

Geprüfte Abwesenheiten
----------------------
Damit niemand dieselbe Frage zweimal stellt (Lauf A des AP17a-Nachtrags,
2026-08-13, Flächen jeweils innerhalb der Bbox):

* **Terra fusca** — der Kalkverwitterungslehm über Devon- und Massenkalk,
  fachlich der naheliegende Kandidat neben Rendzina. Kommt in der BK 50
  **nicht vor**, weder in der Bbox noch landesweit; der Datensatz kennt an
  Terra-Typen ausschliesslich "Terra rossa" (65 ha landesweit, keine Fläche
  in der Bbox). Kein Tabelleneintrag nötig.
* **Geschiebemergel** — landesweit die grösste Kalkfläche NRWs. Steht in der
  GK 100 **nicht in `LITHOLOG_1`**, sondern im Feld `EINHEIT`
  ("Grundmoräne", 1745 Objekte). Deren Lithologie lautet "Schluff, Ton,
  Steine"; dieser Wert hat in der Bbox **keine Fläche** — die Grundmoräne
  liegt vollständig nördlich davon. Für diesen Ausschnitt gegenstandslos.

Offene und geschlossene Punkte der fachlichen Prüfung
-----------------------------------------------------
1. **Offen.** Die Gewichtung der Gesteinsanteile nach Position (unten
   `ANTEIL_GEWICHT`) unterstellt, dass die Reihenfolge in `LITHOLOG_1` die
   Dominanz abbildet. Weder Legende noch Metadatei des Downloads belegen
   das, und weitere Anteils- oder Prozentfelder führt der Datensatz nicht.
   Ebenso unbelegt ist die Abklingfunktion `1/(i+1)` — sie ist eine
   Setzung, keine Ableitung. Beides bleibt offen; geraten wird nicht.
   Klassenwirkung nachweisbar ("Kalkstein, Tonstein" 73,3 gegen "Tonstein,
   Kalkstein" 46,7), in der Bbox aber ohne Fläche: Beide Kombinationen
   kommen dort nicht vor.
2. **Geschlossen.** Bei zusammengesetzten Bodentypen gilt der letzte Teil
   als Haupttyp — das entspricht der KA5-Nomenklatur, in der der Grundtyp
   hinten und der Modifikator vorn steht. Der Nebenbefund dazu ist
   vermessen: Mit `HAUPTTYP_ANTEIL = 0.6` ergibt "Rendzina-Braunerde" genau
   55 und liegt damit knapp unter `BODEN_BESTAETIGT_AB` = 60. Betroffen
   sind 13,87 km² dieses Typs; davon erreichen 1,17 km² überhaupt den
   Rohwert 55, weil der Rest über die Lithologie höher liegt. Beide
   Konstanten bleiben deshalb unverändert — 1,17 km² von 7553 km²
   rechtfertigen keine Justierung, die AP17b ohnehin neu bewertet.
3. **Geschlossen.** Gips und Anhydrit stehen bei 55, dem einzigen
   Tabellenwert knapp über der Schwelle. Die zugehörige Perm-Einheit liegt
   am Ostrand NRWs bei Höxter, weit ausserhalb der Bbox (Ostgrenze 7,2°);
   im Ausschnitt hat sie keine Fläche. Bei einer Erweiterung der Bbox neu
   zu bewerten.
4. **Geschlossen.** Vulkanit (Eifel) steht bei 30 und damit unterhalb der
   Schwelle. Der genaue Wert ist klassenunwirksam, solange er dort bleibt.
"""

# Wert, ab dem eine Fläche als kalkgeprägt gilt. Darunter greift die steile
# Kennlinie und drückt das Ergebnis in die unterste Klasse.
SCHWELLE = 50.0

# Kein Wert heisst hier wirklich "keine Aussage" und nicht "schlecht":
# Anthropogene Aufschüttungen und Gewässer bekommen nodata, nicht 0 — sonst
# behauptet die Karte Kenntnis, die sie nicht hat.
OHNE_AUSSAGE = None

# ---------------------------------------------------------------- Lithologie

# Gesteinsanteile aus IS GK 100, Feld LITHOLOG_1. Vollständig gegenüber dem
# Datenstand; ein unbekannter Anteil führt zu nodata (siehe litho_score).
KALKWERT_LITHOLOGIE: dict[str, float | None] = {
    # --- Carbonatgesteine: der eigentliche Zielstandort
    "Kalkstein": 100,
    "Kalk": 100,
    "Kalksandstein": 85,  # carbonatisch gebundener Sandstein
    "Mergelstein": 80,  # Ton + Carbonat
    "Mergel": 80,
    "Dolomitstein": 85,  # carbonatisch, Mg-betont
    "Dolomit": 85,
    # --- Sulfatgesteine: basenreich, hoher pH, aber kein Carbonat
    "Gips": 55,
    "Anhydrit": 55,
    "Steinsalz": 30,  # kommt nur zusammen mit Carbonat/Sulfat vor
    # --- Lockersedimente mit Carbonatanteil
    "Sand und Löss": 55,  # Löss primär carbonathaltig, oben meist entkalkt
    "Mudde": 30,  # Seesediment, Carbonatanteil sehr wechselhaft
    "Feuersteinschotter": 35,  # Rückstand der Kreide, meist entkalkt
    # --- Ton und Schluff: basenärmer, ausser wenn mergelig (siehe Kombination)
    "Ton": 25,
    "Tonstein": 20,
    "Schluff": 25,
    "Schluffstein": 20,
    # --- Silikatische Locker- und Festgesteine
    "Sand": 10,
    "Sandstein": 10,
    "Kies": 10,
    "Schotter": 10,
    "Steine": 10,
    "Blöcke": 10,
    "Kies und Steine": 10,
    "Quarzit": 5,
    "Quarzkies": 5,
    "Quarzsand": 5,
    "Kaolinsand": 0,
    "Metamorphit": 10,
    "Roteisenstein": 10,
    "Vulkanit": 30,  # Eifel: basenreiche Verwitterung, kalkfrei
    # --- Ausgesprochen saure oder organische Bildungen
    "Kieselschiefer": 0,
    "Alaunschiefer": 0,  # pyrithaltig, versauernd
    "Torf": 0,
    "Braunkohle": 0,
    "Steinkohle": 0,
    # --- Ohne Aussage
    "Gewässer": OHNE_AUSSAGE,
    "Abraum": OHNE_AUSSAGE,
    "Müll": OHNE_AUSSAGE,
    "Bergematerial": OHNE_AUSSAGE,
    "Erdaushub": OHNE_AUSSAGE,
}

# Gewicht der Gesteinsanteile nach ihrer Position in LITHOLOG_1. Der erste
# Anteil zählt voll, jeder weitere mit 1/(i+1) — die Reihenfolge bildet die
# Dominanz ab (siehe offener Punkt 1).
def ANTEIL_GEWICHT(position: int) -> float:  # noqa: N802 — Tabellenname, kein Verb
    return 1.0 / (position + 1)


# ----------------------------------------------------------------- Bodentyp

# Grundtypen aus IS BK 50, Feld TYP_TEXT. Zusammengesetzte Namen werden an
# "-" zerlegt (siehe boden_score).
KALKWERT_BODENTYP: dict[str, float | None] = {
    # --- Kalkbodentypen im engeren Sinn
    "Rendzina": 100,  # Humusauflage direkt auf Carbonatgestein
    "Rendzina in Auenlage": 85,
    "Kalkgley": 85,
    "Pararendzina": 85,  # auf Mergel, Löss, carbonatischem Lockergestein
    "Terra rossa": 70,  # Kalkverwitterungslehm, oben meist entkalkt
    "Tschernosem": 70,  # auf Löss, basenreich
    # --- Tonböden aus Mergel und Kalkstein
    "Pelosol": 60,
    # --- Lössböden: Carbonat meist erst im Unterboden
    "Parabraunerde": 35,
    "Humusparabraunerde": 30,
    # --- Verbreitete, meist basenärmere Typen
    "Braunerde": 25,
    "Humusbraunerde": 20,
    "Auenbraunerde": 25,
    "Braunerde in Auenlage": 25,
    "Humusbraunerde in Auenlage": 20,
    "Vega": 30,  # Auenboden, Carbonat je nach Einzugsgebiet
    "Vega (Braunauenboden)": 30,
    "Paternia": 30,
    "Rambla (Auenlockersyrosem)": 30,
    "Kolluvisol": 30,  # Hangfussmaterial, erbt das Einzugsgebiet
    "Regosol": 20,
    "Regosol in Auenlage": 20,
    "Ranker": 10,  # auf Silikatgestein
    "Syrosem": 15,
    "Lockersyrosem": 15,
    "Lockersyrosem in Auenlage": 15,
    "Skeletthumusboden": 10,
    # --- Staunasse und grundwasserbeeinflusste Typen
    "Pseudogley": 20,
    "Pseudogley in Auenlage": 20,
    "Auenpseudogley": 20,
    "Haftnässepseudogley": 15,
    "Stagnogley": 10,
    "Anmoorstagnogley": 5,
    "Moorstagnogley": 5,
    "Gley": 20,
    "Gley in Auenlage": 20,
    "Auengley": 20,
    "Hanggley": 20,
    "Nassgley": 10,
    "Anmoorgley": 5,
    "Anmoorgley in Auenlage": 5,
    "Humusgley in Auenlage": 10,
    "Niedermoorgley": 5,
    "Hochmoorgley": 0,
    # --- Saure Typen
    "Podsol": 0,
    "Humuspodsol": 0,
    # --- Moore: sauer und nass
    "Moor": 0,
    "Niedermoor": 5,
    "Hochmoor": 0,
    "Übergangs(nieder)moor": 0,
    # --- Anthropogene Typen: Ausgangsmaterial unbekannt
    "Brauner Plaggenesch": 15,
    "Grauer Plaggenesch": 15,
    "Graubrauner Plaggenesch": 15,
    "Deckkulturboden": OHNE_AUSSAGE,
    "Tiefumbruchboden": OHNE_AUSSAGE,
    "Fehnkultur": OHNE_AUSSAGE,
}

# Namenszusätze, die den Bodentyp nicht wechseln. "Auftrags-Pararendzina"
# ist eine aufgetragene Pararendzina, kein eigener Typ.
BODEN_ZUSAETZE = frozenset({"Auftrags", "Abtrags", "Erd"})

# Anteil des letztgenannten Teils bei zusammengesetzten Bodentypen. Die
# Daten führen beide Reihenfolgen ("Rendzina-Braunerde" und
# "Braunerde-Rendzina"), die Reihenfolge trägt also Bedeutung; der zweite
# Teil gilt als Haupttyp — KA5-Nomenklatur, siehe Punkt 2 im Docstring.
HAUPTTYP_ANTEIL = 0.6

# Verknüpfung der beiden Quellen innerhalb der Kaskadenstufe 2.
#
# **Kein Mittelwert.** Der erste Anlauf hat beide Quellen gemittelt, und das
# Ergebnis war fachlich falsch: Über den Eifelkalkmulden (Blankenheim,
# Nettersheim) steht in der BK 50 meist schlicht "Braunerde" — die
# Bodentypbezeichnung sagt dort nichts über Carbonat aus, drückte im Mittel
# aber Kalkstein aus der Klasse "gut" in die Klasse "gering".
#
# Die beiden Quellen sagen Unterschiedliches:
#
# * Die **Lithologie** ist der belastbare positive Anzeiger. Wo Kalkstein
#   ansteht, ist Carbonat im Wurzelraum, ob der Boden nun Rendzina oder
#   Braunerde heisst.
# * Der **Bodentyp** ist nur dort aussagekräftig, wo er selbst ein
#   Kalkbodentyp ist (Rendzina, Pararendzina, Kalkgley) — dann bestätigt er
#   und kann eine im Massstab 1:100.000 übersehene Kalklinse nachtragen —
#   oder wo er den Standort tatsächlich überschreibt: Moor, Nassgley und
#   Podsol sind sauer und nass, unabhängig vom Untergrund.
BODEN_BESTAETIGT_AB = 60.0
BODEN_UEBERSCHREIBT_BIS = 10.0

# Wo der Bodentyp nichts über Carbonat sagt (Braunerde, Parabraunerde,
# Gley …), bleibt die Lithologie massgeblich — gedämpft, weil eine mächtige
# Lössdecke den Kalk aus dem Wurzelraum halten kann.
#
# **Die Dämpfung greift nach der Kennlinie, nicht davor** (AP17a-Nachtrag,
# B1). Davor angewandt wirkte die Konstante nicht wie 0,85: Die Kennlinie
# spreizt oberhalb der Schwelle mit 1,5, wodurch aus 0,85 auf dem Rohwert
# ein Faktor von gemessen 0,743 bis 0,775 auf dem ausgelieferten Score
# wurde — abhängig davon, wo der Rohwert lag, also nicht einmal konstant.
# Eine benannte Konstante soll bedeuten, was sie sagt; hinter der Kennlinie
# tut sie das.
#
# Wirkung des Umbaus, gemessen an den Faktorlayern vom 2026-08-13: 43,26 km²
# wechseln von Klasse 3 nach 4, keine Fläche wechselt in anderer Richtung.
# Unterhalb der Schwelle ändert sich nichts — dort ist die Kennlinie linear
# durch den Ursprung, beide Reihenfolgen sind gleichwertig.
#
# Der Wert 0,85 selbst bleibt unbelegt und gehört auf die Kalibrierliste für
# Phase 3.
DAEMPFUNG_OHNE_AUSSAGE = 0.85


def _zerlege(wert: str, trenner: str) -> list[str]:
    return [teil.strip() for teil in wert.split(trenner) if teil.strip()]


def litho_score(lithologie: str | None) -> float | None:
    """Kalkscore einer Lithologie-Angabe aus IS GK 100.

    Unbekannter Anteil -> None (nodata), nicht 0. Eine Lücke in der Tabelle
    soll als Lücke in der Karte auffallen und nicht als schlechter Standort
    durchgehen.
    """
    if not lithologie:
        return None

    summe = 0.0
    gewichte = 0.0
    for position, anteil in enumerate(_zerlege(lithologie, ",")):
        if anteil not in KALKWERT_LITHOLOGIE:
            return None
        wert = KALKWERT_LITHOLOGIE[anteil]
        if wert is None:
            return None
        gewicht = ANTEIL_GEWICHT(position)
        summe += wert * gewicht
        gewichte += gewicht

    return summe / gewichte if gewichte else None


def _grundtyp(teil: str) -> str:
    # Führendes "=" ist eine Schreibweise der Quelle und kein Namensteil.
    return teil.lstrip("=").strip()


def boden_score(bodentyp: str | None) -> float | None:
    """Kalkscore eines Bodentyps aus IS BK 50.

    Enthält ein zusammengesetzter Name einen Teil ohne Aussage, wird der
    **ganze** Wert zu None — geprüft und so belassen (AP17a-Nachtrag B3).
    Betroffen sind "Abtrags-Hochmoor-Deckkulturboden" (1,95 km²) und
    "Niedermoor-Deckkulturboden" (0,42 km²), zusammen 2,37 km² von
    7553 km². In beiden steht der Deckkulturboden **hinten** und ist damit
    nach der Konvention dieser Datei der Haupttyp: Was oben liegt, ist
    aufgebrachtes Material unbekannter Herkunft. Aus dem verschütteten
    Untergrund einen Kalkwert abzuleiten hiesse, über den heutigen
    Wurzelraum etwas zu behaupten, das die Quelle nicht hergibt.

    Fiele der Teil ohne Aussage einmal an eine andere Stelle als hinten,
    wäre die Regel neu zu prüfen; in diesem Datenstand kommt das nicht vor.
    """
    if not bodentyp or not bodentyp.strip():
        return None

    teile = [_grundtyp(t) for t in _zerlege(bodentyp, "-")]
    teile = [t for t in teile if t not in BODEN_ZUSAETZE]
    if not teile:
        return None

    werte: list[float] = []
    for teil in teile:
        if teil not in KALKWERT_BODENTYP:
            return None
        wert = KALKWERT_BODENTYP[teil]
        if wert is None:
            return None
        werte.append(float(wert))

    if len(werte) == 1:
        return werte[0]

    # Letzter Teil ist der Haupttyp, die davor teilen sich den Rest.
    haupt = werte[-1]
    neben = sum(werte[:-1]) / len(werte[:-1])
    return HAUPTTYP_ANTEIL * haupt + (1.0 - HAUPTTYP_ANTEIL) * neben


def kennlinie(rohwert: float) -> float:
    """Steile Kennlinie statt K.-o.-Kriterium (ADR 0008 §4).

    Unterhalb von SCHWELLE wird der Wert auf die unterste Klasse (0-25)
    gestaucht, oberhalb auf 25-100 gespreizt. Die Fläche verschwindet nie —
    sie wird nur deutlich abgewertet, und der Grund bleibt über den
    Faktorlayer nachvollziehbar (Invariante 10).
    """
    wert = max(0.0, min(100.0, rohwert))
    if wert < SCHWELLE:
        return wert * (25.0 / SCHWELLE)
    return 25.0 + (wert - SCHWELLE) * (75.0 / (100.0 - SCHWELLE))


def verknuepft(litho: float | None, boden: float | None) -> tuple[float | None, bool]:
    """Lithologie und Bodentyp zu einem Rohwert — **ungedämpft**.

    Zweiter Rückgabewert: ob der Schweige-Zweig gegriffen hat, der Bodentyp
    also weder bestätigt noch überschreibt. Nur dann wird später gedämpft —
    und zwar hinter der Kennlinie, siehe DAEMPFUNG_OHNE_AUSSAGE.

    Siehe die Begründung bei BODEN_BESTAETIGT_AB: Der Bodentyp bestätigt,
    überschreibt oder schweigt — gemittelt wird nicht.
    """
    if litho is None and boden is None:
        return None, False
    if boden is None:
        return litho, False
    if litho is None:
        return boden, False

    if boden >= BODEN_BESTAETIGT_AB:
        # Kalkbodentyp: bestätigt die Lithologie und kann eine im
        # 1:100.000 übersehene Kalklinse nachtragen.
        return max(litho, boden), False
    if boden <= BODEN_UEBERSCHREIBT_BIS:
        # Sauer und nass schlägt den Untergrund.
        return min(litho, boden), False
    return max(litho, boden), True


def kalkscore(lithologie: str | None, bodentyp: str | None) -> float | None:
    """Kaskadenstufe 2: IS GK 100 und IS BK 50 zusammen (ADR 0008 §5).

    Liegt nur eine der beiden Quellen vor, trägt sie allein — das ist immer
    noch Stufe 2, nur auf schmalerer Grundlage. Fehlen beide, bleibt die
    Zelle leer.

    Reihenfolge: erst die Kennlinie auf den ungedämpften Rohwert, dann die
    Dämpfung. Andersherum verschiebt die Spreizung der Kennlinie die
    Bedeutung der Konstante (AP17a-Nachtrag B1).
    """
    roh, schweigt = verknuepft(litho_score(lithologie), boden_score(bodentyp))
    if roh is None:
        return None
    score = kennlinie(roh)
    return score * DAEMPFUNG_OHNE_AUSSAGE if schweigt else score
