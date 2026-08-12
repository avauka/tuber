import type { BasiskartenMeta } from "../shared/typen";

type Props = {
  meta: BasiskartenMeta | null;
};

/**
 * Attribution — Pflicht und dauerhaft sichtbar (Spec §15).
 *
 * Bewusst ein eigener Streifen und nicht MapLibres einklappbares Control:
 * Eine Pflichtangabe, die hinter einem „i" verschwindet, ist keine.
 *
 * Der Datenstand kommt aus `basemap.meta.json` und damit aus den Metadaten
 * im Archiv selbst — nicht aus dem Dateinamen und nicht aus einer Konstante,
 * die beim nächsten Extract still veraltet.
 */
export function Attribution({ meta }: Props) {
  return (
    <div className="attribution">
      <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
        © OpenStreetMap
      </a>{" "}
      contributors (ODbL) ·{" "}
      <a href="https://protomaps.com" target="_blank" rel="noreferrer">
        Protomaps
      </a>
      {meta && (
        <>
          {" "}
          · Datenstand {new Date(meta.osm_data_timestamp).toLocaleDateString("de-DE")} · Tileset{" "}
          {meta.tileset_version}
        </>
      )}
    </div>
  );
}
