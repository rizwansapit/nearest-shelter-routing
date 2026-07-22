\set ON_ERROR_STOP on

\echo
\echo 'Road table summary'
\echo '------------------'

SELECT
    COUNT(*) AS road_count,
    ROUND(SUM(length_m)::numeric / 1000, 3) AS total_length_km,
    ROUND(MIN(length_m)::numeric, 3) AS shortest_segment_m,
    ROUND(MAX(length_m)::numeric, 3) AS longest_segment_m
FROM routing.roads;


\echo
\echo 'Geometry validation'
\echo '-------------------'

SELECT
    ST_SRID(geometry) AS srid,
    GeometryType(geometry) AS geometry_type,
    COUNT(*) AS feature_count
FROM routing.roads
GROUP BY
    ST_SRID(geometry),
    GeometryType(geometry)
ORDER BY geometry_type;


SELECT
    COUNT(*) FILTER (
        WHERE geometry IS NULL
    ) AS null_geometries,

    COUNT(*) FILTER (
        WHERE ST_IsEmpty(geometry)
    ) AS empty_geometries,

    COUNT(*) FILTER (
        WHERE NOT ST_IsValid(geometry)
    ) AS invalid_geometries,

    COUNT(*) FILTER (
        WHERE length_m <= 0
    ) AS zero_length_roads
FROM routing.roads;


\echo
\echo 'Routing cost validation'
\echo '-----------------------'

SELECT
    COUNT(*) FILTER (
        WHERE cost IS NULL
    ) AS null_forward_cost,

    COUNT(*) FILTER (
        WHERE reverse_cost IS NULL
    ) AS null_reverse_cost,

    COUNT(*) FILTER (
        WHERE cost <= 0
    ) AS invalid_forward_cost,

    COUNT(*) FILTER (
        WHERE reverse_cost <= 0
    ) AS invalid_reverse_cost
FROM routing.roads;


\echo
\echo 'Road indexes'
\echo '------------'

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'routing'
  AND tablename = 'roads'
ORDER BY indexname;