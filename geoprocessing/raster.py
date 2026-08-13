"""Das gemeinsame Zielraster (ADR 0008 §1, §2).

**Einmal hier definiert, von allen Faktoren geteilt.** Wenn zwei Faktorlayer
auch nur um eine halbe Zelle gegeneinander verschoben sind, addiert Stufe 2
später Werte, die nicht zur selben Stelle gehören — und niemand sieht es der
fertigen Karte an.

Die Ausdehnung stammt aus der Bbox 5.4,49.7,7.2,51.1 (dieselbe wie die
Basiskarte aus AP10a), transformiert nach EPSG:25832 und auf ganze
20-m-Zellen ausgerichtet. Die Zahlen stehen **fest im Code** statt bei jedem
Lauf neu transformiert zu werden: Eine neue PROJ-Version darf das Raster
nicht um Zentimeter verschieben und damit alle bestehenden Faktorlayer
unbrauchbar machen.

Berechnet am 2026-08-13 mit GDAL 3.13.2 / PROJ, Ecken und Kantenmitten der
Bbox transformiert, Minimum abgerundet und Maximum aufgerundet auf 20 m:

    min/max x   240424.449 / 373970.781  ->  240420 / 373980
    min/max y  5506831.413 / 5667110.997 -> 5506820 / 5667120

Modul ohne Abhängigkeiten: reine Arithmetik, damit die Prüfung der
Rastergeometrie keinen GDAL-Import braucht.
"""

from dataclasses import dataclass

# Bbox in Grad, wie in ADR 0002 und AP10a. Nur zur Dokumentation der
# Herkunft — gerechnet wird mit den Metern unten.
BBOX_WGS84 = (5.4, 49.7, 7.2, 51.1)

EPSG = 25832

# 20 m statt der 10 m aus Spec §6 (ADR 0008 §2): Ein Viertel der Datenmenge,
# und drei der sechs Faktoren liefern ohnehin nur 50 m bis 1 km.
ZELLGROESSE_M = 20

MIN_X = 240_420
MIN_Y = 5_506_820
MAX_X = 373_980
MAX_Y = 5_667_120


@dataclass(frozen=True)
class Rasterbezug:
    """Ausdehnung und Auflösung — alles, was ein Faktorlayer teilen muss."""

    min_x: int = MIN_X
    min_y: int = MIN_Y
    max_x: int = MAX_X
    max_y: int = MAX_Y
    zellgroesse: int = ZELLGROESSE_M
    epsg: int = EPSG

    @property
    def spalten(self) -> int:
        return (self.max_x - self.min_x) // self.zellgroesse

    @property
    def zeilen(self) -> int:
        return (self.max_y - self.min_y) // self.zellgroesse

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        """GDAL-Geotransform: Ursprung oben links, y läuft nach unten."""
        return (
            float(self.min_x),
            float(self.zellgroesse),
            0.0,
            float(self.max_y),
            0.0,
            -float(self.zellgroesse),
        )

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def passt_zu(self, geotransform: tuple[float, ...], spalten: int, zeilen: int) -> bool:
        """Prüft ein vorhandenes Raster gegen diesen Bezug.

        Stufe 2 liest Faktorlayer, die in verschiedenen Läufen entstanden
        sein können. Bevor sie addiert werden, muss feststehen, dass sie
        dieselben Zellen meinen.
        """
        return (
            spalten == self.spalten
            and zeilen == self.zeilen
            and tuple(geotransform) == self.geotransform
        )


ZIELRASTER = Rasterbezug()
