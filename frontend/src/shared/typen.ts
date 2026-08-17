/** Spiegel der Antwort-Schemas des Backends (app/schemas/*). */

export type Fund = {
  id: string;
  client_uuid: string;
  lat: number;
  lon: number;
  gps_accuracy_m: number;
  found_at: string;
  session_id: string | null;
  species_guess: string;
  species_confidence: string;
  phenotype: string;
  id_pending: boolean;
  maturity: string;
  calcium_reaction: string;
  revisit_due: string | null;
  notes: string | null;
  created_at: string;
};

export type Signal = {
  id: string;
  client_uuid: string;
  lat: number;
  lon: number;
  signal_type: string;
  observed_at: string | null;
  dog_confidence: string | null;
  session_id: string | null;
  notes: string | null;
};

/** GeoJSON-Polygon, so wie POST /api/areas es erwartet. */
export type Polygon = {
  type: "Polygon";
  coordinates: [number, number][][];
};

/**
 * Saisonzustand eines Gebiets (AP-Saisonzustand, ADR 0007 „Rückweg").
 *
 * Zweite, getrennte Größe neben der Bedingungs-Engine: sechs Monate
 * Rückschau aus dem ERA5-Archiv gegen eine 30-Jahres-Normale. Beantwortet
 * „ist dieses Jahr eins", nicht „ist jetzt ein guter Zeitpunkt".
 */
export type Saisonzustand = {
  window_end: string;
  precipitation_30d_mm: number | null;
  precipitation_90d_mm: number | null;
  precipitation_180d_mm: number | null;
  precipitation_30d_percent: number | null;
  precipitation_90d_percent: number | null;
  precipitation_180d_percent: number | null;
  soil_moisture_90d: number | null;
  soil_moisture_90d_percent: number | null;
  dry_spell_days: number | null;
  complete: boolean;
  missing_days: number;
  reference_from_year: number;
  reference_to_year: number;
  source: string;
};

export type Gebiet = {
  id: string;
  name: string;
  geometry: Polygon;
  notes: string | null;
  access_notes: string | null;
  last_visited: string | null;
  offline_pinned: boolean;
  area_m2: number;
  /** Fehlt, solange der monatliche Backfill für das Gebiet nicht lief. */
  season?: Saisonzustand | null;
};

export type GebietEntwurf = {
  name: string;
  geometry: Polygon;
  notes: string | null;
  access_notes: string | null;
  offline_pinned: boolean;
};

/** basemap.meta.json, geschrieben vom Extract-Job (AP10a). */
export type BasiskartenMeta = {
  build_date: string;
  osm_data_timestamp: string;
  tileset_version: string;
  bbox: number[];
  maxzoom: number;
  bytes: number;
  sha256: string;
  fetched_at: string;
};

/** suitability.meta.json, geschrieben von geoprocessing/stufe2_tiles.py. */
export type EignungsMeta = {
  gewichtssatz_version: number;
  faktoren: Record<string, number>;
  faktoren_fehlend: string[];
  rasterweite_m: number | null;
  klassengrenzen: number[];
  quellen: { name?: string; herausgeber?: string; lizenz?: string; stand?: string }[];
  generated_at: string;
};

/** Was beim Antippen einer Eignungsfläche sichtbar wird (Invariante 10). */
export type EignungsTreffer = {
  score: number;
  klasse: number;
  stufe: number;
  teilscores: Record<string, number>;
};
