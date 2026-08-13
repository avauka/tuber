"""Faktorgewichte und Klasseneinteilung (ADR 0008 §3, §5).

Die Gewichte stehen hier als Startsatz, damit Stufe 2 auch ohne laufende
Datenbank rechnen kann. **Verbindlich ist der aktive Satz in der Datenbank**
(Tabelle `suitability_weight_set`, `GET /api/suitability/weights`); die
erzeugten Kacheln halten die verwendete Version in `suitability.meta.json`
fest. Ohne diese Notiz liesse sich später nicht rekonstruieren, welche Karte
zu welchem Fund gehörte (ADR 0008 §7).

Reine Arithmetik, keine Abhängigkeiten — damit die Umlage-Regel geprüft
werden kann, ohne GDAL zu starten.
"""

VERSION = 1

# ADR 0008 §3. Summe 100.
GEWICHTE: dict[str, float] = {
    "kalk": 30.0,
    "wasser": 20.0,
    "exposition": 15.0,
    "wirtsbaum": 15.0,
    "struktur": 10.0,
    "klima": 10.0,
}

# Vier diskrete Klassen, kein Farbverlauf (Spec §6): Ein glatter Verlauf
# suggeriert eine Trennschärfe, die abgeleitete Daten nicht hergeben.
# Untergrenzen, Klasse 1 beginnt bei 0.
KLASSENGRENZEN = (25.0, 50.0, 75.0)

KLASSEN_TEXT = {
    1: "gering",
    2: "mäßig",
    3: "gut",
    4: "sehr gut",
}


def umgelegt(vorhandene_faktoren: list[str], satz: dict[str, float] | None = None) -> dict[str, float]:
    """Gewichte auf die tatsächlich vorhandenen Faktoren umlegen.

    Fällt ein Faktor aus, wird sein Gewicht **proportional** auf die
    übrigen verteilt (ADR 0008 §5) — kein Ersatzwert, kein Auffüllen mit
    Mittelwerten, das würde eine Aussage erfinden.

    Bei nur einem Faktor bedeutet das: Er trägt 100 %. Das ist richtig
    gerechnet und muss im UI erklärt werden, sonst sieht die Karte nach
    sechs Faktoren aus und zeigt einen.
    """
    quelle = satz if satz is not None else GEWICHTE
    unbekannt = [name for name in vorhandene_faktoren if name not in quelle]
    if unbekannt:
        raise ValueError(f"Unbekannte Faktoren: {', '.join(sorted(unbekannt))}")
    if not vorhandene_faktoren:
        raise ValueError("Ohne Faktoren gibt es keinen Score.")

    summe = sum(quelle[name] for name in vorhandene_faktoren)
    if summe <= 0:
        raise ValueError("Die vorhandenen Faktoren haben zusammen das Gewicht 0.")

    return {name: quelle[name] * 100.0 / summe for name in vorhandene_faktoren}


def klasse(score: float) -> int:
    """Score 0-100 in eine der vier Klassen."""
    for nummer, grenze in enumerate(KLASSENGRENZEN, start=1):
        if score < grenze:
            return nummer
    return len(KLASSENGRENZEN) + 1
