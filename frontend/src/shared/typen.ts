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

export type Gebiet = {
  id: string;
  name: string;
  geometry: Polygon;
  notes: string | null;
  access_notes: string | null;
  last_visited: string | null;
  offline_pinned: boolean;
  area_m2: number;
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
