import json
import signal
import sys
import time
from datetime import datetime, timezone

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from confluent_kafka import Producer
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_API_KEY = os.getenv("KAFKA_API_KEY")
KAFKA_API_SECRET = os.getenv("KAFKA_API_SECRET")
TOPIC = "weather-raw"
POLL_INTERVAL_SECONDS = 30

CITY = {
    "name": "Palmerston North",
    "lat": -40.35,
    "lon": 175.61,
}

API_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
    "precipitation,pressure_msl,cloud_cover"
    "&timezone=Pacific/Auckland"
)

running = True


def signal_handler(sig, frame):
    global running
    print("\nShutting down producer...")
    running = False


def delivery_callback(err, msg):
    if err:
        print(f"Delivery failed: {err}")
    else:
        print(f"Delivered to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")


def create_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


session = create_session()


def fetch_weather(city):
    url = API_URL.format(lat=city["lat"], lon=city["lon"])
    response = session.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    current = data["current"]
    return {
        "city": city["name"],
        "latitude": city["lat"],
        "longitude": city["lon"],
        "temperature_c": current["temperature_2m"],
        "humidity_pct": current["relative_humidity_2m"],
        "wind_speed_kmh": current["wind_speed_10m"],
        "precipitation_mm": current["precipitation"],
        "pressure_hpa": current["pressure_msl"],
        "cloud_cover_pct": current["cloud_cover"],
        "observed_at": current["time"],
    }


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    kafka_config = {"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS}
    if KAFKA_API_KEY and KAFKA_API_SECRET:
        kafka_config.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": KAFKA_API_KEY,
            "sasl.password": KAFKA_API_SECRET,
        })
    producer = Producer(kafka_config)
    print(f"Weather producer started. Polling every {POLL_INTERVAL_SECONDS}s for {CITY['name']}.")

    while running:
        try:
            weather = fetch_weather(CITY)
            producer.produce(
                TOPIC,
                key=weather["city"].encode("utf-8"),
                value=json.dumps(weather).encode("utf-8"),
                callback=delivery_callback,
            )
            producer.poll(0)
            print(f"[{datetime.now(timezone.utc).isoformat()}] {weather['city']}: {weather['temperature_c']}°C")
        except requests.RequestException as e:
            print(f"API error for {CITY['name']}: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        for _ in range(POLL_INTERVAL_SECONDS):
            if not running:
                break
            time.sleep(1)

    producer.flush(timeout=5)
    print("Producer shut down.")


if __name__ == "__main__":
    main()
