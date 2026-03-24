import json
import os
from datetime import datetime, timezone

import requests
from confluent_kafka import Producer

KAFKA_BOOTSTRAP_SERVERS = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
KAFKA_API_KEY = os.environ["KAFKA_API_KEY"]
KAFKA_API_SECRET = os.environ["KAFKA_API_SECRET"]
TOPIC = "weather-raw"

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


def fetch_weather(city):
    url = API_URL.format(lat=city["lat"], lon=city["lon"])
    response = requests.get(url, timeout=10)
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


def handler(event, context):
    weather = fetch_weather(CITY)

    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": KAFKA_API_KEY,
        "sasl.password": KAFKA_API_SECRET,
    })

    producer.produce(
        TOPIC,
        key=weather["city"].encode("utf-8"),
        value=json.dumps(weather).encode("utf-8"),
    )
    producer.flush(timeout=10)

    print(f"[{datetime.now(timezone.utc).isoformat()}] {weather['city']}: {weather['temperature_c']}°C")

    return {
        "statusCode": 200,
        "body": json.dumps(weather),
    }
