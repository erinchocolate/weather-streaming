-- 1. Create a stream from the raw weather topic
CREATE STREAM weather_raw_stream (
    city            VARCHAR KEY,
    latitude        DOUBLE,
    longitude       DOUBLE,
    temperature_c   DOUBLE,
    humidity_pct    DOUBLE,
    wind_speed_kmh  DOUBLE,
    precipitation_mm DOUBLE,
    pressure_hpa    DOUBLE,
    cloud_cover_pct DOUBLE,
    observed_at     VARCHAR
) WITH (
    KAFKA_TOPIC = 'weather-raw',
    VALUE_FORMAT = 'JSON'
);

-- 2. Create a 5-minute tumbling window aggregation
CREATE TABLE weather_5min_avg
WITH (KAFKA_TOPIC = 'weather-aggregated', VALUE_FORMAT = 'JSON') AS
SELECT
    city,
    WINDOWSTART    AS window_start,
    WINDOWEND      AS window_end,
    AVG(temperature_c)   AS avg_temperature,
    AVG(humidity_pct)     AS avg_humidity,
    AVG(wind_speed_kmh)   AS avg_wind_speed,
    COUNT(*)              AS reading_count
FROM weather_raw_stream
WINDOW TUMBLING (SIZE 5 MINUTES)
GROUP BY city
EMIT CHANGES;
