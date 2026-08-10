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

# Confidence-Klassen der Coverage aus mittlerer GPS-Genauigkeit der
# behaltenen Punkte. Fehlt jede Genauigkeitsangabe: niedrig.
COVERAGE_CONFIDENCE_HIGH_MAX_M = 10.0
COVERAGE_CONFIDENCE_MEDIUM_MAX_M = 20.0

# --- Bedingungs-Scoring (Spec §5) -----------------------------------------
# Gewichte der vier Teilscores; Summe = 100. Bleiben einzeln sichtbar
# (Invariante 10: kein Score ohne Aufschlüsselung).
SCORE_MAX_SEASON = 30.0
SCORE_MAX_SOIL_MOISTURE = 30.0
SCORE_MAX_RAIN = 25.0
SCORE_MAX_FIELD = 15.0

# Bodenfeuchte in 7-28 cm Tiefe (m³/m³, Open-Meteo). Stückweise lineare
# Glockenkurve: zu trocken ist so schlecht wie zu nass (Staunässe).
SOIL_MOISTURE_OPTIMUM_M3M3 = 0.28
SOIL_MOISTURE_DRY_ZERO_M3M3 = 0.08
SOIL_MOISTURE_WET_ZERO_M3M3 = 0.55

# Regen-Nachlauf: ergiebiger Regen wirkt verzögert, nicht am selben Tag.
# Gewicht 1.0 im Idealfenster, davor/danach linear abfallend.
RAIN_LAG_IDEAL_FROM_DAYS = 3
RAIN_LAG_IDEAL_TO_DAYS = 7
RAIN_LAG_MAX_DAYS = 14
RAIN_WEIGHT_TODAY = 0.2
RAIN_WEIGHT_OLDEST = 0.1
# Ab dieser gewichteten Regensumme gibt es die volle Punktzahl.
RAIN_SATURATION_MM = 25.0

# Feldfaktoren. Gefrorener Boden macht die Suche sinnlos (Spec §5).
FIELD_SOIL_FROZEN_C = 0.0
FIELD_TEMP_IDEAL_FROM_C = 5.0
FIELD_TEMP_IDEAL_TO_C = 20.0
FIELD_TEMP_COLD_ZERO_C = -5.0
FIELD_TEMP_HEAT_ZERO_C = 35.0
FIELD_WIND_CALM_KMH = 15.0
FIELD_WIND_ZERO_KMH = 60.0

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
