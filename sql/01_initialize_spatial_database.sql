\set ON_ERROR_STOP on

-- Enable geospatial and routing extensions.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

-- Create a dedicated schema for project tables.
CREATE SCHEMA IF NOT EXISTS routing
AUTHORIZATION shelter_app;

-- Use the project schema by default for the application role.
ALTER ROLE shelter_app
IN DATABASE nearest_shelter_db
SET search_path = routing, public;

-- Display the configuration result.
SELECT
    current_database() AS database_name,
    current_user AS configured_by;

SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname IN ('postgis', 'pgrouting')
ORDER BY extname;

SELECT
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name = 'routing';