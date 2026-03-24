-- Latest weather reading
SELECT city, temperature_c, humidity_pct, wind_speed_kmh, observed_at
FROM weather_raw
ORDER BY observed_at DESC
LIMIT 1;

-- Temperature trend: readings over time
SELECT observed_at, temperature_c, humidity_pct, wind_speed_kmh
FROM weather_raw
ORDER BY observed_at;

-- Hourly averages
SELECT
    date_trunc('hour', observed_at) AS hour,
    AVG(temperature_c)   AS avg_temp,
    MIN(temperature_c)   AS min_temp,
    MAX(temperature_c)   AS max_temp,
    AVG(humidity_pct)     AS avg_humidity,
    AVG(wind_speed_kmh)   AS avg_wind
FROM weather_raw
GROUP BY 1
ORDER BY 1;

-- 5-minute aggregation results from ksqlDB
SELECT city, window_start, window_end, avg_temperature, avg_wind_speed, reading_count
FROM weather_aggregated
ORDER BY window_start DESC
LIMIT 20;

-- Total readings ingested
SELECT
    COUNT(*) AS total_readings,
    MIN(observed_at) AS first_reading,
    MAX(observed_at) AS last_reading
FROM weather_raw;
