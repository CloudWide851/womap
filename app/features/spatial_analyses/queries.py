from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause


SPATIAL_SUMMARY_SQL = """
WITH input AS (
  SELECT ST_SetSRID(ST_GeomFromGeoJSON(:target), 3857) AS target_3857
), analysis AS (
  SELECT
    target_3857,
    ST_Transform(target_3857, 4326) AS target_4326,
    ST_Transform(target_3857, 4326)::geography AS target_geog,
    ST_Buffer(
      ST_Transform(target_3857, 4326)::geography,
      :distance
    )::geometry AS buffer_4326
  FROM input
), candidates AS (
  SELECT
    c.id,
    c.geom,
    ST_Transform(c.geom, 4326) AS geom_4326,
    GeometryType(c.geom) AS geom_type
  FROM map_features c CROSS JOIN analysis a
  WHERE c.layer_id = :layer_id
    AND NOT (c.layer_id = :target_layer_id AND c.id = :target_feature_id)
    {selection_sql}
    AND c.geom && ST_Transform(ST_Envelope(a.buffer_4326), 3857)
    AND ST_DWithin(
      ST_Transform(c.geom, 4326)::geography,
      a.target_geog,
      :distance
    )
), measured AS (
  SELECT
    c.*,
    ST_Intersects(c.geom, a.target_3857) AS direct_hit,
    ST_Intersects(c.geom_4326, a.buffer_4326) AS buffer_hit,
    ST_Distance(c.geom_4326::geography, a.target_geog) AS distance_m,
    CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
      ST_Area(ST_Intersection(c.geom_4326, a.target_4326)::geography)
      ELSE 0 END AS direct_area,
    CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
      ST_Area(ST_Intersection(c.geom_4326, a.buffer_4326)::geography)
      ELSE 0 END AS buffer_area,
    CASE WHEN c.geom_type IN ('POLYGON', 'MULTIPOLYGON') THEN
      ST_Area(c.geom_4326::geography) ELSE 0 END AS candidate_area,
    CASE WHEN c.geom_type IN ('LINESTRING', 'MULTILINESTRING') THEN
      ST_Length(ST_Intersection(c.geom_4326, a.target_4326)::geography)
      ELSE 0 END AS direct_length,
    CASE WHEN c.geom_type IN ('LINESTRING', 'MULTILINESTRING') THEN
      ST_Length(ST_Intersection(c.geom_4326, a.buffer_4326)::geography)
      ELSE 0 END AS buffer_length
  FROM candidates c CROSS JOIN analysis a
)
SELECT
  COUNT(*)::bigint AS hit_count,
  MIN(distance_m) AS nearest_distance_m,
  COUNT(*) FILTER (WHERE direct_hit)::bigint AS direct_count,
  COUNT(*) FILTER (WHERE buffer_hit)::bigint AS buffer_count,
  COALESCE(SUM(direct_area), 0) AS direct_area_sqm,
  COALESCE(SUM(buffer_area), 0) AS buffer_area_sqm,
  COALESCE(SUM(candidate_area), 0) AS candidate_area_sqm,
  COALESCE(SUM(direct_length), 0) AS direct_length_m,
  COALESCE(SUM(buffer_length), 0) AS buffer_length_m,
  COUNT(*) FILTER (WHERE geom_type IN ('POINT', 'MULTIPOINT'))::bigint AS point_count
FROM measured
"""


def build_spatial_summary_statement(selection_sql: str = "") -> TextClause:
    return text(SPATIAL_SUMMARY_SQL.format(selection_sql=selection_sql))
