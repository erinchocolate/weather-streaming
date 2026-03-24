CREATE TABLE IF NOT EXISTS weather_raw (
    id              SERIAL PRIMARY KEY,
    city            VARCHAR(50) NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    temperature_c   DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    wind_speed_kmh  DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    pressure_hpa    DOUBLE PRECISION,
    cloud_cover_pct DOUBLE PRECISION,
    observed_at     TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weather_aggregated (
    id              SERIAL PRIMARY KEY,
    city            VARCHAR(50) NOT NULL,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    avg_temperature DOUBLE PRECISION,
    avg_humidity    DOUBLE PRECISION,
    avg_wind_speed  DOUBLE PRECISION,
    reading_count   INTEGER,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_raw_city_time ON weather_raw(city, observed_at);
CREATE INDEX idx_agg_city_window ON weather_aggregated(city, window_start);
