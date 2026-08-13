# ADR 0008 — Eignungskarte: Quellen, Gewichtung, Kaskade

**Datum:** 2026-08-12 · **Status:** angenommen, drei Punkte offen (Abschnitt 9)

Konkretisiert Spec §6. Wo diese Entscheidung vom Spec abweicht, ist es einzeln
begründet und markiert.

---

## 1. Entscheidung in Kürze

Ein artunabhängiges Eignungsraster für die Gattung *Tuber*, offline
vorberechnet, **20 m Rasterweite**, EPSG:25832, ausgeliefert als Tiles. Sechs
gewichtete Faktoren, je Faktor eine Fallback-Kaskade, je Zelle eine
protokollierte Herkunftsstufe. Kein Ausschlusskriterium innerhalb des Scores.
Die Zugänglichkeit überschreibt das Ergebnis visuell.

## 2. Rasterweite: 20 m statt 10 m

Spec §6 nennt 10 m, limitiert durch die Baumartendaten. Auf 20 m reduziert:

- Die Datenmenge sinkt gegenüber 10 m auf ein Viertel, gegenüber DGM1 auf ein
  Vierhundertstel. Das entscheidet darüber, ob die Pipeline auf einem
  Arbeitsrechner überhaupt praktikabel ist.
- Die schwächsten Faktoren liegen bei 50 m (Boden) und 1 km (Klima). Ein
  10-m-Ergebnisraster suggeriert eine Trennschärfe, die drei von sechs Faktoren
  nicht liefern.
- Die Karte beantwortet „wohin fahre ich", nicht „wo genau im Bestand". Für die
  zweite Frage war sie nie gedacht.

**Preis:** Schmale Hangkanten und einzelne Waldrandsäume verschwinden. Bewusst
akzeptiert.

## 3. Faktoren und Gewichte

| Faktor | Gewicht | Spec §6 |
|---|---|---|
| Kalk / pH | 30 % | unverändert |
| Wasserhaushalt / Drainage | 20 % | unverändert |
| Exposition / Einstrahlung | 15 % | unverändert |
| Wirtsbaum | 15 % | war 25 % |
| Bestandsstruktur | 10 % | neu |
| Klima | 10 % | unverändert |

**Warum der Wirtsbaum von 25 auf 15 fällt.** Der Thünen-Layer kennt nur die
dominante Kronenbaumart, sieht die Hasel im Unterwuchs nicht (Spec §13, Punkt 3)
und sein Aufnahmestand liegt vor dem Fichtensterben ab 2018. Ein Viertel des
Gesamtscores auf einer Größe mit dieser Fehlerlage überzeichnet ihre
Belastbarkeit.

**Warum die Bestandsstruktur die 10 Punkte bekommt.** nDOM50 (Geobasis NRW,
0,5 m Bodenauflösung, Differenz aus DGM und belaubtem bDOM) liefert die relative
Objekthöhe über Gelände, im Wald also die Bestandshöhe. Daraus: Kronendachdichte,
Bestandslücken, Waldränder, Übergänge zwischen offener Kalkfläche und
Hallenwald. Unabhängig gemessen, aktueller als die Baumartenkarte, und näher an
dem, was Trüffelstandorte auszeichnet als die Artzusammensetzung allein.

**Kein weiterer Faktor.** Die FFH-/Biotopdaten des LANUV bleiben ein Overlay
neben dem Score, nicht darin: Die Kartierung ist lückenhaft, und wo nichts
kartiert wurde, liegt nicht zwangsläufig kein Kalk. Als Zahl im Score würde eine
Erhebungslücke zum Standortnachteil. Als Overlay ist sie ehrliche
Zusatzinformation — und wo Kalk-Trockenrasen oder Orchideen-Kalkbuchenwald
kartiert sind, hat jemand vor Ort nachgesehen. Das schlägt jede Ableitung.

## 4. Kein Ausschluss im Score — Kennlinie statt Schalter

Geprüft und **verworfen**: Kalkboden als K.-o.-Kriterium, Nadelwald als
Ausschluss.

**Kalk.** Die Kalkbindung ist fachlich nahezu bindend — *T. aestivum* ist
ausgeprägt calcicol. Der Einwand ist nicht biologisch, sondern datenseitig:
Spec §13 Punkt 2 hält fest, dass der pH-Wert aus Geologie und Bodentyp
**abgeleitet** ist, nicht gemessen. Bei 1:50.000 verschwinden Mergellinsen,
Kolluvium am Hangfuß, alte Kalkung und kleinräumige Wechsel. Ein hartes K.o. auf
einem abgeleiteten Wert löscht solche Stellen unwiderruflich aus der Karte — der
Nutzer sieht sie nie und erfährt nie, dass er sie nicht sieht.

Stattdessen: **steile, nicht-lineare Kennlinie.** Unterhalb der Schwelle fällt
der Gesamtscore in die unterste Klasse; die Fläche bleibt sichtbar, der Grund
bleibt aufschlüsselbar (Invariante 10), und ein HCl-Tropfen im Feld kann der
Karte widersprechen.

**Nadelwald.** Ein Ausschluss wäre sachlich falsch. *Tuber*-Arten bilden auch
mit Kiefer und Fichte Mykorrhiza, und *T. borchii* ist ausgesprochen
kiefernaffin — Spec §5 nennt für ihr Januar-bis-April-Fenster ausdrücklich
Kiefer und Hasel. Da die Karte laut Spec §6 für die **Gattung** gilt, würde ein
Nadelwald-Ausschluss ausgerechnet das Frühjahrsfenster wegschneiden.

Hinzu kommt eine Doppelzählung: Fichtenforste der Eifel stehen überwiegend auf
sauren Standorten und fallen bereits über den Kalkfaktor heraus. Ein zweiter
Ausschluss über die Baumart träfe zusätzlich die Kiefer auf Kalk — genau den
Standort, der im Februar zählt.

**Ein echtes K.o. gibt es nur außerhalb des Scores:** Sperrflächen
(Truppenübungsplätze, Nationalpark-Kernzonen, Schutzgebiete mit Betretungs-
verbot) werden schraffiert und überschreiben die Darstellung — Spec §6.

## 5. Fallback-Kaskade und Datenqualitäts-Ampel

Jede Zelle protokolliert je Faktor die verwendete Stufe. Die Ampel entsteht
daraus, nicht aus einer Schätzung.

**Kalk / pH**
1. IS GK 100 Lithologie + FSK 5 — NRW, wo BK 5 F vorliegt
2. IS GK 100 + FSK 50 / IS BK 50 — NRW flächendeckend
3. BFD50 (LGB Rheinland-Pfalz) — RLP flächendeckend
4. SoilGrids 250 m (ISRIC, CC-BY)

**Wasserhaushalt / Drainage**
1. FSK 5 Gesamtwasserhaushalt — direkt enthalten, keine Ableitung nötig
2. IS BK 50 (Staunässe, Durchwurzelbarkeit) — abgeleitet
3. BFD50
4. SoilGrids

**Wirtsbaum**
1. Thünen Dominant Tree Species (10 m), maskiert mit der **Kalamitätskarte NRW**
   (Nadelholz-Vitalitätsverlust seit 2018, Flächen ab 0,1 ha, Schadstufe 3 =
   abgestorben oder geräumt)
2. Thünen ohne Maske — außerhalb NRW
3. Faktor entfällt

**Bestandsstruktur**
1. nDOM50 (NRW)
2. Faktor entfällt

**Exposition / Einstrahlung**
1. DGM aus Laserscanning, auf 20 m aggregiert
2. Faktor entfällt

**Klima**
1. DWD 1-km-Raster, vieljährige Mittel

**Regel bei Ausfall:** Das Gewicht eines entfallenden Faktors wird proportional
auf die vorhandenen umgelegt, und die Zelle wird in der Ampel abgestuft. Kein
Ersatzwert, kein Auffüllen mit Mittelwerten — das würde eine Aussage erfinden.

**Keine Klassenübersetzung zwischen Kartenwerken.** Statt FSK-5- auf
BFD50-Klassen abzubilden, bekommt jede Quelle **eigene Regeln auf dieselbe
0–100-Skala**. Eine Übersetzungstabelle zwischen zwei Systematiken wäre eine
Fehlerquelle, die niemand mehr prüfen kann. Eine sichtbare Kante an der
Landesgrenze bleibt möglich; sie ist über die Ampel erklärbar und damit
ehrlicher als eine geglättete Naht.

## 6. Wallonien: keine Eignungskarte, dafür ein Overlay

Invariante 12 verbietet, CNSW-Daten zu proxyen oder zu cachen. Ein
vorberechnetes Raster, das diese Daten verarbeitet und von unserem Server als
Tiles ausgeliefert wird, ist ein abgeleitetes Produkt und fällt unter dieselbe
Beschränkung.

**Entscheidung:** Das Eignungsraster deckt NRW und Rheinland-Pfalz ab. Für den
wallonischen Teil der Bbox gibt es keine Eignungskarte. Stattdessen wird CNSW
als **client-seitiges WMS-Overlay** im Planer angeboten — Textur, Drainage,
Steingehalt, direkt vom wallonischen Dienst geladen, nie über unseren Server.

**Verworfen:** Wallonien mit SoilGrids und ohne Baum-/Strukturfaktor
mitzurechnen. Vier von sechs Faktoren fehlten dort in ihrer guten Stufe; die
Karte sähe vollständiger aus, als sie ist. Ein Loch, das als Loch sichtbar ist,
schadet weniger als eine Fläche, die Präzision vortäuscht.

**Verworfen:** die Lizenz zu brechen. Erwogen und bewusst abgelehnt — der
Gewinn wäre ein Faktor von sechs in dem Gebiet mit ohnehin schwächster
Datenlage, während die Attribution bei fünf anderen Quellen sichtbar eingehalten
wird.

## 7. Zweistufige Pipeline und kalibrierbare Gewichte

Die Gewichte müssen nachträglich änderbar sein — Spec §5 fordert das bereits für
die Saisonkurven, Spec §11 sieht Gewichtsanpassung ab etwa 30 Funden vor.
Daraus folgt der Aufbau:

**Stufe 1 — teuer, selten.** Quellen laden, reprojizieren, auf das gemeinsame
20-m-Raster bringen, je Faktor einen normierten Layer 0–100 erzeugen, dazu je
Zelle die Herkunftsstufe. Läuft, wenn eine Quelle neu ist. Tagesmaßstab.

**Stufe 2 — billig, oft.** Die sechs Faktorlayer gewichtet aufsummieren und
Tiles schreiben. Minuten.

Eine Gewichtsänderung löst nur Stufe 2 aus. Ohne diese Trennung wäre Kalibrierung
praktisch unmöglich. Nebeneffekt: Die Faktorlayer aus Stufe 1 **sind** die von
Invariante 10 geforderte Aufschlüsselung.

**Ablage der Gewichte.** CLAUDE.md verlangt kalibrierbare Konstanten in
`backend/app/core/params.py`. Die Konvention wird präzisiert, nicht gebrochen:
`params.py` für strukturelle Konstanten (Buffer, Genauigkeitsschwelle,
Cluster-Radius), **Datenbank** für zur Laufzeit änderbare Scoring-Parameter.

**Versionierung, nicht verhandelbar.** Gewichtssätze tragen Version und
Zeitstempel; die erzeugten Tiles halten in `suitability.meta.json` fest, mit
welcher Version sie entstanden sind — dasselbe Muster wie `basemap.meta.json`
und derselbe Gedanke wie das Einfrieren von `session.conditions_score`. Ohne das
lässt sich in Phase 3 nicht rekonstruieren, welche Karte zu welchem Fund gehörte.

## 8. Rohdatenhaltung

Rohdaten (DGM, FSK, BFD50, Thünen-Raster, Kalamitätskarte, nDOM50) berühren den
Server nie. Sie werden lokal verarbeitet, auf dem Volume landet nur die fertige
Kachelpyramide plus `suitability.meta.json`. Das ist die Voraussetzung dafür,
dass ein 5-GB-Volume überhaupt reicht.

DGM1 liegt bei Geobasis NRW als GeoTIFF-Kacheln offen vor. Die Pipeline
aggregiert kachelweise auf 20 m und verwirft das Original sofort, statt erst
alles zu laden und dann zu rechnen.

## 9. Offene Punkte

1. **Gröberes DGM.** Ob Geobasis NRW ein offen herunterladbares DGM zwischen
   1 m und 50 m anbietet, konnte nicht abschließend geklärt werden. DGM50 wird
   für abgeleitete Produkte genannt; ob es als eigener Open-Data-Download
   existiert, ist offen. Ohne das bleibt DGM1 mit Sofort-Aggregation der Weg.
2. **Relief in Rheinland-Pfalz.** Verfügbarkeit und Lizenz eines DGM des LGB
   RLP sind nicht geprüft.
3. **Bezugsformat der Kalamitätskarte.** Als Open Data gelistet, Downloadformat
   und Aktualitätsstand noch zu prüfen.

Keiner dieser Punkte blockiert die Entscheidung; alle drei betreffen die
Beschaffung in AP17.

## 10. Konsequenzen

- Spec §6 wird angepasst: Rasterweite 20 m, sechs Faktoren mit neuen Gewichten,
  Fallback-Kaskade, Wallonien ohne Eignungsraster.
- Spec §13 bekommt zwei weitere bekannte Grenzen: der Baumartenlayer ist auch
  **zeitlich** veraltet (Fichtensterben ab 2018, außerhalb NRW unkorrigiert),
  und für Wallonien gibt es keine Eignungskarte.
- AP17 wird zweistufig geschnitten.
- Die Settings-Seite (eigenes Paket, nach AP18) trennt sichtbar zwischen sofort
  wirksamen Parametern (Saisonkurven) und solchen, die einen Pipeline-Lauf
  brauchen (Faktorgewichte).

## 11. Attribution (Pflicht, sichtbar; ergänzt Spec §15)

- Geologischer Dienst NRW — IS GK 100, IS BK 50, IS BK 5 / FSK 5, FSK 50,
  IS BK 5 Übersicht · dl-de/by-2-0, mit Abrufdatum
- Landesamt für Geologie und Bergbau Rheinland-Pfalz — BFD50 ·
  dl-de/by-2-0, „©LGB-RLP (Jahr des Datenbezugs)"
- Geobasis NRW — DGM, nDOM50
- Thünen-Institut — Dominant Tree Species (Blickensdörfer et al. 2024)
- Waldinfo.NRW / LANUV — Kalamitätskarte
- LANUV — LINFOS, FFH-Lebensraumtypen · dl-de/by-2-0
- DWD Climate Data Center
- ISRIC SoilGrids · CC-BY
- Service public de Wallonie (CNSW) — **nur client-seitig**, nicht
  redistribuierbar
