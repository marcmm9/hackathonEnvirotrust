-- DDL Schema for TimescaleDB / PostgreSQL

-- 1. Assets Table (Solar Park Metadata)
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    capacity_mw NUMERIC(10,2) NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    year_built INT NOT NULL,
    area_ha NUMERIC(10,2) NOT NULL,
    operator VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for spatial queries
CREATE INDEX IF NOT EXISTS idx_assets_coordinates ON assets(latitude, longitude);

-- 2. Climate Metrics Table (Hourly Time-Series)
CREATE TABLE IF NOT EXISTS climate_metrics_hourly (
    asset_id INT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature_2m REAL,
    wind_speed_10m REAL,
    shortwave_radiation REAL,
    weather_code SMALLINT,
    PRIMARY KEY (asset_id, timestamp)
);

-- Convert to TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('climate_metrics_hourly', 'timestamp', if_not_exists => TRUE);

-- Composite index for temporal lookups
CREATE INDEX IF NOT EXISTS idx_climate_hourly_asset_time ON climate_metrics_hourly(asset_id, timestamp DESC);

-- 3. Financial Audit Trail Table (Revisionssicherheit)
CREATE TABLE IF NOT EXISTS financial_audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id INT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    simulation_timestamp TIMESTAMPTZ DEFAULT NOW(),
    simulated_year INT NOT NULL,
    capacity_multiplier REAL NOT NULL,
    production_mwh NUMERIC(12,2) NOT NULL,
    revenue_eur NUMERIC(12,2) NOT NULL,
    opex_eur NUMERIC(12,2) NOT NULL,
    debt_service_eur NUMERIC(12,2) NOT NULL,
    net_profit_eur NUMERIC(12,2) NOT NULL,
    dscr REAL NOT NULL,
    covenant_breached BOOLEAN NOT NULL,
    simulation_parameters JSONB NOT NULL
);

-- Index for audit retrievals
CREATE INDEX IF NOT EXISTS idx_audit_asset_year ON financial_audit_trail(asset_id, simulated_year);
