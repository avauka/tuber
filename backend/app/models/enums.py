"""DB-Enums, Werte exakt wie Spec §4/§4a (deutsch, snake_case).

ACHTUNG baumart_enum: Das Spec referenziert das Enum, definiert aber keine
Werteliste. Die Liste unten ist ein VORSCHLAG (regionale Trüffel-Wirtsbäume)
und muss vom Nutzer fachlich abgenommen werden, bevor echte Daten entstehen.
Erweiterung ist billig (ALTER TYPE ADD VALUE), Umbenennung nicht.
"""

import enum


class ArtEnum(str, enum.Enum):
    t_aestivum = "t_aestivum"  # Sommer-/Burgundertrüffel (EINE Art, Invariante 7)
    t_macrosporum = "t_macrosporum"
    t_mesentericum = "t_mesentericum"
    t_borchii = "t_borchii"
    t_brumale = "t_brumale"
    t_rufum = "t_rufum"  # Indikatorart, nie ausfiltern (Invariante 8)
    t_excavatum = "t_excavatum"  # Indikatorart, nie ausfiltern (Invariante 8)
    t_melanosporum = "t_melanosporum"
    tuber_spec = "tuber_spec"  # Feld-Default (Invariante 6)
    andere_hypogaee = "andere_hypogaee"


class SpeciesConfidenceEnum(str, enum.Enum):
    sicher = "sicher"
    wahrscheinlich = "wahrscheinlich"
    vermutung = "vermutung"
    unbestimmt = "unbestimmt"


class PhenotypeEnum(str, enum.Enum):
    """Ökotyp, nur bei T. aestivum relevant. Saisonlogik hängt HIER, nie an der Art."""

    sommer = "sommer"
    burgunder = "burgunder"
    unbestimmt = "unbestimmt"


class MaturityEnum(str, enum.Enum):
    unreif = "unreif"
    reif = "reif"
    ueberreif = "ueberreif"
    unbestimmt = "unbestimmt"


class BaumartEnum(str, enum.Enum):
    """VORSCHLAG — fachliche Abnahme ausstehend, siehe Modul-Docstring."""

    eiche = "eiche"
    buche = "buche"
    hainbuche = "hainbuche"
    hasel = "hasel"
    linde = "linde"
    birke = "birke"
    kiefer = "kiefer"
    fichte = "fichte"
    pappel = "pappel"
    weide = "weide"
    sonstige = "sonstige"
    unbekannt = "unbekannt"


class CalciumReactionEnum(str, enum.Enum):
    stark = "stark"
    schwach = "schwach"
    keine = "keine"
    ungetestet = "ungetestet"


class SignalTypeEnum(str, enum.Enum):
    hund_anzeige_ohne_fund = "hund_anzeige_ohne_fund"
    truffelfliege = "truffelfliege"
    brule_erkannt = "brule_erkannt"
    habitat_auffaellig = "habitat_auffaellig"
    wirtsbaum_bestand = "wirtsbaum_bestand"


class DogConfidenceEnum(str, enum.Enum):
    stark = "stark"
    mittel = "mittel"
    schwach = "schwach"


class SubjectiveRatingEnum(str, enum.Enum):
    gut = "gut"
    mittel = "mittel"
    schlecht = "schlecht"


class TrackSourceEnum(str, enum.Enum):
    gpx_import = "gpx_import"
    native = "native"
    manuell = "manuell"


class CoverageConfidenceEnum(str, enum.Enum):
    hoch = "hoch"
    mittel = "mittel"
    niedrig = "niedrig"


class MediaKindEnum(str, enum.Enum):
    photo = "photo"
    voice = "voice"
