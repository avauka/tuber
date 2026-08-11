"""Datenmodell nach Spec §4/§4a.

Abweichungen vom Spec-Schema, bewusst und dokumentiert:
- find.client_uuid / signal.client_uuid: UNIQUE, für Idempotenz der
  Offline-Queue (Invariante 3, Spec §12). §4 listet das Feld nicht, §12
  verlangt es.
- find.gps_accuracy_m ist NOT NULL (Invariante 1: kein Fund ohne
  Genauigkeitsangabe).
- Wiederbesuchs-Erinnerungen werden auf Fundstellen-Ebene aggregiert
  (Abfrage-Schicht, MIN über 15-m-Cluster) — revisit_due bleibt trotzdem
  pro Fund gespeichert, wie im Spec.
"""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models import enums


def _enum(e: type, name: str) -> Enum:
    """PG-Enum mit stabilen Werten (nicht Python-Namen) anlegen."""
    return Enum(e, name=name, values_callable=lambda x: [i.value for i in x])


_uuid_pk = lambda: mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Session(Base):
    __tablename__ = "session"

    id: Mapped[uuid.UUID] = _uuid_pk()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Spec-Luecke (Migration 0002): §5 verlangt das Einfrieren der Bedingungen
    # beim Session-Ende, dafuer braucht die Session das Gebiet. §4 listet das
    # Feld nicht.
    area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("area.id"))
    area_label: Mapped[str | None] = mapped_column(Text)
    dog_name: Mapped[str | None] = mapped_column(Text)
    dog_work_minutes: Mapped[int | None] = mapped_column(Integer)
    temperature_c: Mapped[float | None] = mapped_column(Numeric)
    wind_kmh: Mapped[float | None] = mapped_column(Numeric)
    soil_moisture_0_7: Mapped[float | None] = mapped_column(Numeric)
    precip_prev_7d_mm: Mapped[float | None] = mapped_column(Numeric)
    conditions_score: Mapped[float | None] = mapped_column(Numeric)
    subjective_rating: Mapped[enums.SubjectiveRatingEnum | None] = mapped_column(
        _enum(enums.SubjectiveRatingEnum, "subjective_rating_enum")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class Find(Base):
    __tablename__ = "find"

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    geom: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    # Invariante 1: nie ohne Genauigkeit speichern.
    gps_accuracy_m: Mapped[float] = mapped_column(Numeric, nullable=False)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session.id"))
    species_guess: Mapped[enums.ArtEnum] = mapped_column(
        _enum(enums.ArtEnum, "art_enum"),
        default=enums.ArtEnum.tuber_spec,
        server_default=enums.ArtEnum.tuber_spec.value,
    )
    species_confidence: Mapped[enums.SpeciesConfidenceEnum] = mapped_column(
        _enum(enums.SpeciesConfidenceEnum, "species_confidence_enum"),
        default=enums.SpeciesConfidenceEnum.unbestimmt,
        server_default=enums.SpeciesConfidenceEnum.unbestimmt.value,
    )
    phenotype: Mapped[enums.PhenotypeEnum] = mapped_column(
        _enum(enums.PhenotypeEnum, "phenotype_enum"),
        default=enums.PhenotypeEnum.unbestimmt,
        server_default=enums.PhenotypeEnum.unbestimmt.value,
    )
    # Invariante 6: Feld-Default ist offene Bestimmung.
    id_pending: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    weight_g: Mapped[float | None] = mapped_column(Numeric)
    depth_cm: Mapped[float | None] = mapped_column(Numeric)
    maturity: Mapped[enums.MaturityEnum] = mapped_column(
        _enum(enums.MaturityEnum, "maturity_enum"),
        default=enums.MaturityEnum.unbestimmt,
        server_default=enums.MaturityEnum.unbestimmt.value,
    )
    host_tree: Mapped[enums.BaumartEnum | None] = mapped_column(
        _enum(enums.BaumartEnum, "baumart_enum")
    )
    host_distance_m: Mapped[float | None] = mapped_column(Numeric)
    soil_ph_measured: Mapped[float | None] = mapped_column(Numeric)
    calcium_reaction: Mapped[enums.CalciumReactionEnum] = mapped_column(
        _enum(enums.CalciumReactionEnum, "calcium_reaction_enum"),
        default=enums.CalciumReactionEnum.ungetestet,
        server_default=enums.CalciumReactionEnum.ungetestet.value,
    )
    brule_present: Mapped[bool | None] = mapped_column(Boolean)
    truffle_fly: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    photo_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    voice_note_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    revisit_due: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow
    )


class Signal(Base):
    """Signal ohne Fund — eigene Tabelle, für den Lernkreislauf (Spec §4)."""

    __tablename__ = "signal"

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    geom: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session.id"))
    signal_type: Mapped[enums.SignalTypeEnum] = mapped_column(
        _enum(enums.SignalTypeEnum, "signal_type_enum"), nullable=False
    )
    dog_confidence: Mapped[enums.DogConfidenceEnum | None] = mapped_column(
        _enum(enums.DogConfidenceEnum, "dog_confidence_enum")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    photo_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    voice_note_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))


class Track(Base):
    __tablename__ = "track"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("session.id"))
    geom: Mapped[object] = mapped_column(
        Geography(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=False
    )
    source: Mapped[enums.TrackSourceEnum] = mapped_column(
        _enum(enums.TrackSourceEnum, "track_source_enum"), nullable=False
    )
    source_filename: Mapped[str | None] = mapped_column(Text)
    recorded_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recorded_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    point_count: Mapped[int | None] = mapped_column(Integer)
    mean_accuracy_m: Mapped[float | None] = mapped_column(Numeric)
    length_m: Mapped[float | None] = mapped_column(Numeric)


class Coverage(Base):
    """Materialisiert aus BEREINIGTEN Tracks (Invariante 5)."""

    __tablename__ = "coverage"

    id: Mapped[uuid.UUID] = _uuid_pk()
    track_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("track.id"))
    geom: Mapped[object] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False), nullable=False
    )
    buffer_m: Mapped[float] = mapped_column(Numeric, server_default=text("8"))
    covered_at: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[enums.CoverageConfidenceEnum | None] = mapped_column(
        _enum(enums.CoverageConfidenceEnum, "coverage_confidence_enum")
    )


class Area(Base):
    __tablename__ = "area"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    geom: Mapped[object] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    access_notes: Mapped[str | None] = mapped_column(Text)
    last_visited: Mapped[date | None] = mapped_column(Date)
    offline_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )


class Media(Base):
    __tablename__ = "media"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[enums.MediaKindEnum] = mapped_column(
        _enum(enums.MediaKindEnum, "media_kind_enum"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geom: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    duration_s: Mapped[float | None] = mapped_column(Numeric)
    transcript: Mapped[str | None] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class ConditionsSnapshot(Base):
    __tablename__ = "conditions_snapshot"
    __table_args__ = (UniqueConstraint("area_id", "date", name="uq_conditions_area_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    soil_moisture_0_7: Mapped[float | None] = mapped_column(Numeric)
    soil_moisture_7_28: Mapped[float | None] = mapped_column(Numeric)
    soil_temp_7_28: Mapped[float | None] = mapped_column(Numeric)
    precip_mm: Mapped[float | None] = mapped_column(Numeric)
    temp_mean_c: Mapped[float | None] = mapped_column(Numeric)
    # Spec-Luecke (Migration 0003): §5 fuehrt wind_speed_10m als Ingest-Variable
    # und das Feld-Scoring braucht Wind, §4 gibt conditions_snapshot aber keine
    # Spalte dafuer.
    wind_kmh: Mapped[float | None] = mapped_column(Numeric)
    # Roharchiv der API-Antwort. Bewusst nur Archiv: gelesen wird aus den
    # Spalten, damit kein JSONB-Schluessel zur stillen Verabredung wird.
    raw: Mapped[dict | None] = mapped_column(JSONB)


class BackupDownload(Base):
    """Nachweis, dass ein Dump das Volume verlassen hat (ADR 0004, AP15).

    Nicht im Spec — Spec §4 kennt keine Backup-Tabelle. Ohne diesen Nachweis
    laesst sich aber nicht unterscheiden, ob ein Dump nur existiert oder
    tatsaechlich off-platform liegt; genau das ist der Unterschied zwischen
    einem Backup und einer Datei auf demselben Volume.
    """

    __tablename__ = "backup_download"

    id: Mapped[uuid.UUID] = _uuid_pk()
    filename: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
