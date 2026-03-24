import json
import os
import signal
import sys
from datetime import datetime, timezone

import psycopg2
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_API_KEY = os.getenv("KAFKA_API_KEY")
KAFKA_API_SECRET = os.getenv("KAFKA_API_SECRET")
TOPICS = ["weather-raw", "weather-aggregated"]

PG_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "dbname": os.getenv("POSTGRES_DB", "weatherdb"),
    "user": os.getenv("POSTGRES_USER", "weather"),
    "password": os.getenv("POSTGRES_PASSWORD", "weather123"),
}

running = True


def signal_handler(sig, frame):
    global running
    print("\nShutting down consumer...")
    running = False


def insert_raw(cur, data):
    cur.execute(
        """INSERT INTO weather_raw
           (city, latitude, longitude, temperature_c, humidity_pct,
            wind_speed_kmh, precipitation_mm, pressure_hpa, cloud_cover_pct, observed_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            data["city"],
            data["latitude"],
            data["longitude"],
            data["temperature_c"],
            data["humidity_pct"],
            data["wind_speed_kmh"],
            data["precipitation_mm"],
            data["pressure_hpa"],
            data["cloud_cover_pct"],
            data["observed_at"],
        ),
    )


def insert_aggregated(cur, data, city):
    window_start = datetime.fromtimestamp(data["WINDOW_START"] / 1000, tz=timezone.utc)
    window_end = datetime.fromtimestamp(data["WINDOW_END"] / 1000, tz=timezone.utc)
    cur.execute(
        """INSERT INTO weather_aggregated
           (city, window_start, window_end, avg_temperature, avg_humidity,
            avg_wind_speed, reading_count)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            city,
            window_start,
            window_end,
            data.get("AVG_TEMPERATURE", data.get("avg_temperature")),
            data.get("AVG_HUMIDITY", data.get("avg_humidity")),
            data.get("AVG_WIND_SPEED", data.get("avg_wind_speed")),
            data.get("READING_COUNT", data.get("reading_count")),
        ),
    )


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    kafka_config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "weather-pg-writer",
        "auto.offset.reset": "earliest",
    }
    if KAFKA_API_KEY and KAFKA_API_SECRET:
        kafka_config.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": KAFKA_API_KEY,
            "sasl.password": KAFKA_API_SECRET,
        })
    consumer = Consumer(kafka_config)
    consumer.subscribe(TOPICS)
    print(f"Consumer started. Subscribed to: {TOPICS}")

    while running:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            print(f"Consumer error: {msg.error()}")
            continue

        try:
            data = json.loads(msg.value().decode("utf-8"))
            topic = msg.topic()

            if topic == "weather-raw":
                insert_raw(cur, data)
                print(f"[raw] {data['city']}: {data['temperature_c']}°C, {data['humidity_pct']}% humidity, {data['wind_speed_kmh']} km/h wind")
            elif topic == "weather-aggregated":
                # ksqlDB windowed key = city string + 8 bytes window timestamp
                raw_key = msg.key()
                city = raw_key[:-8].decode("utf-8") if raw_key and len(raw_key) > 8 else "unknown"
                insert_aggregated(cur, data, city)
                avg_temp = data.get("AVG_TEMPERATURE", data.get("avg_temperature"))
                avg_hum = data.get("AVG_HUMIDITY", data.get("avg_humidity"))
                avg_wind = data.get("AVG_WIND_SPEED", data.get("avg_wind_speed"))
                print(f"[agg] {city}: avg {avg_temp:.1f}°C, avg {avg_hum:.0f}% humidity, avg {avg_wind:.1f} km/h wind")
        except Exception as e:
            print(f"Error processing message: {e}")

    consumer.close()
    cur.close()
    conn.close()
    print("Consumer shut down.")


if __name__ == "__main__":
    main()
