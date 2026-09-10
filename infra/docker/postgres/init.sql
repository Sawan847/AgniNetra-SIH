-- =============================================================================
-- AgniNetra AI — PostgreSQL Initialization
-- This script runs once when the database container is first created.
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify PostGIS installation
DO $$
BEGIN
    RAISE NOTICE 'PostGIS version: %', PostGIS_Full_Version();
    RAISE NOTICE 'UUID extension ready: %', (SELECT extversion FROM pg_extension WHERE extname = 'uuid-ossp');
END
$$;
