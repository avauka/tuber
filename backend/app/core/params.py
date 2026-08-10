"""Kalibrierbare Domänen-Konstanten.

Alle Werte sind Startwerte und werden nach den ersten echten Felddaten
kalibriert (siehe Backlog). Nie inline duplizieren — immer von hier importieren.
"""

from datetime import timedelta

# --- Coverage (Spec §9) ---------------------------------------------------
# Effektive Suchbreite des Hundes um den Track. Achtung: addiert sich nicht
# mit dem GPS-Fehler unterm Kronendach — Confidence-Klasse fängt das ab.
COVERAGE_BUFFER_M = 8.0

# --- Track-Bereinigung (Spec §9) ------------------------------------------
# Punkte mit gemeldeter Genauigkeit oberhalb dieser Schwelle werden verworfen.
# Nach den ersten ~3 echten Tracks prüfen: unter dichtem Kronendach evtl. zu
# streng (fragmentierte Tracks -> löchrige Coverage).
TRACK_ACCURACY_MAX_M = 25.0

# Ausreißerfilter über Geschwindigkeitsplausibilität. NICHT im Spec —
# Vorschlag: Fußsuche mit Hund, >3 m/s über mehrere Punkte ist GPS-Sprung.
TRACK_SPEED_MAX_MS = 3.0

# GPX liefert oft nur <hdop> (dimensionslos) statt Meter. Daumenregel-Faktor
# zur Umrechnung; Ergebnis wird als Schätzung gekennzeichnet (ADR 0006).
HDOP_TO_M_FACTOR = 5.0

# --- Feld-Logging (Invariante 1/2) ----------------------------------------
# Oberhalb dieser gemeldeten Genauigkeit wird das Loggen blockiert. iOS ohne
# "Genauer Standort" liefert 3-9 km — jede Schwelle im niedrigen dreistelligen
# Meterbereich trennt das sauber.
FIND_ACCURACY_BLOCK_M = 100.0

# --- Fundstellen & Wiederbesuch (Spec §10) --------------------------------
# Räumliches Clustering mehrerer Funde zu einer Fundstelle.
FIND_CLUSTER_RADIUS_M = 15.0

# revisit_due = found_at + 1 Jahr - 3 Wochen. Erinnerungen werden auf
# Fundstellen-Ebene aggregiert (MIN über den Cluster), nicht pro Einzelfund —
# sonst erzeugen drei Funde an einer Stelle drei Erinnerungen.
REVISIT_OFFSET = timedelta(days=365 - 21)
