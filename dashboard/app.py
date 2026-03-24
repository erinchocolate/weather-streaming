import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv

load_dotenv()

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_API_KEY = os.getenv("KAFKA_API_KEY")
KAFKA_API_SECRET = os.getenv("KAFKA_API_SECRET")


def create_consumer(group_suffix):
    config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": f"dashboard-{group_suffix}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    }
    if KAFKA_API_KEY and KAFKA_API_SECRET:
        config.update({
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": KAFKA_API_KEY,
            "sasl.password": KAFKA_API_SECRET,
        })
    return Consumer(config)


@st.cache_resource
def get_data_store():
    """Shared data store that persists across Streamlit reruns."""
    return {
        "raw": deque(maxlen=500),
        "aggregated": deque(maxlen=100),
        "latest": None,
        "lock": threading.Lock(),
    }


@st.cache_resource
def start_consumer_thread():
    """Start a background thread that continuously consumes from Kafka."""
    store = get_data_store()

    def consume_loop():
        consumer = create_consumer("live")
        consumer.subscribe(["weather-raw", "weather-aggregated"])

        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                continue

            try:
                data = json.loads(msg.value().decode("utf-8"))
                topic = msg.topic()

                with store["lock"]:
                    if topic == "weather-raw":
                        store["raw"].append(data)
                        store["latest"] = data
                    elif topic == "weather-aggregated":
                        raw_key = msg.key()
                        city = raw_key[:-8].decode("utf-8") if raw_key and len(raw_key) > 8 else "unknown"
                        data["city"] = city
                        store["aggregated"].append(data)
            except Exception:
                continue

    thread = threading.Thread(target=consume_loop, daemon=True)
    thread.start()
    return thread


# ── Start consumer ──
start_consumer_thread()
store = get_data_store()

# ── Page Config ──
st.set_page_config(page_title="Chicken Coop Weather Monitor", layout="wide")
st.title("Chicken Coop Weather Monitor")
st.caption("Palmerston North - Real-time weather monitoring for coop management")

# ── Auto-refresh ──
refresh_seconds = st.sidebar.slider("Auto-refresh interval (seconds)", 5, 60, 10)
st.sidebar.caption(f"Dashboard refreshes every {refresh_seconds}s")

# ── Latest Reading ──
st.header("Current Conditions")

with store["lock"]:
    latest = store["latest"]
    raw_list = list(store["raw"])
    agg_list = list(store["aggregated"])

if latest:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Temperature", f"{latest['temperature_c']}°C")
    col2.metric("Humidity", f"{latest['humidity_pct']}%")
    col3.metric("Wind Speed", f"{latest['wind_speed_kmh']} km/h")
    col4.metric("Precipitation", f"{latest['precipitation_mm']} mm")

    col5, col6, col7 = st.columns(3)
    col5.metric("Pressure", f"{latest['pressure_hpa']} hPa")
    col6.metric("Cloud Cover", f"{latest['cloud_cover_pct']}%")
    col7.metric("Last Updated", latest["observed_at"])

    # Chicken comfort assessment
    temp = float(latest["temperature_c"])
    humidity = float(latest["humidity_pct"])

    st.subheader("Coop Status")
    if temp > 30:
        st.error("HIGH TEMPERATURE - Chickens are at risk of heat stress. Increase ventilation and provide cool water.")
    elif temp > 25:
        st.warning("Warm conditions - Monitor chickens for panting. Ensure shade and water are available.")
    elif temp < 2:
        st.error("FREEZING RISK - Risk of frostbite on combs. Activate heat lamp and close vents.")
    elif temp < 8:
        st.warning("Cold conditions - Consider closing coop vents overnight.")
    else:
        st.success(f"Comfortable range ({temp}°C) - Ideal conditions for chickens.")

    if humidity > 80:
        st.warning("High humidity - Risk of respiratory issues. Improve coop ventilation.")
else:
    st.info("Waiting for data from Kafka... (data arrives every ~1 minute)")

# ── Temperature Trend ──
st.header("Temperature Trend")

if len(raw_list) > 1:
    trend_df = pd.DataFrame(raw_list)
    trend_df["temperature_c"] = pd.to_numeric(trend_df["temperature_c"])
    trend_df["humidity_pct"] = pd.to_numeric(trend_df["humidity_pct"])
    trend_df["wind_speed_kmh"] = pd.to_numeric(trend_df["wind_speed_kmh"])
    trend_df["observed_at"] = pd.to_datetime(trend_df["observed_at"])

    tab1, tab2, tab3 = st.tabs(["Temperature", "Humidity", "Wind Speed"])

    with tab1:
        st.line_chart(trend_df.set_index("observed_at")["temperature_c"], y_label="°C")
    with tab2:
        st.line_chart(trend_df.set_index("observed_at")["humidity_pct"], y_label="%")
    with tab3:
        st.line_chart(trend_df.set_index("observed_at")["wind_speed_kmh"], y_label="km/h")
else:
    st.info(f"Collecting data... ({len(raw_list)} readings so far)")

# ── 5-Minute Aggregates ──
st.header("5-Minute Averages (ksqlDB)")

if agg_list:
    agg_df = pd.DataFrame(agg_list)
    agg_df["avg_temperature"] = pd.to_numeric(agg_df.get("AVG_TEMPERATURE", agg_df.get("avg_temperature", 0)))
    agg_df["avg_humidity"] = pd.to_numeric(agg_df.get("AVG_HUMIDITY", agg_df.get("avg_humidity", 0)))
    agg_df["avg_wind_speed"] = pd.to_numeric(agg_df.get("AVG_WIND_SPEED", agg_df.get("avg_wind_speed", 0)))
    agg_df["reading_count"] = pd.to_numeric(agg_df.get("READING_COUNT", agg_df.get("reading_count", 0)))

    window_start_col = "WINDOW_START" if "WINDOW_START" in agg_df.columns else "window_start"
    agg_df["window_start"] = pd.to_datetime(
        pd.to_numeric(agg_df[window_start_col]), unit="ms", utc=True
    )

    # Show only final aggregate per window
    final_agg = agg_df.loc[agg_df.groupby("window_start")["reading_count"].idxmax()]
    final_agg = final_agg.sort_values("window_start", ascending=False)

    st.dataframe(
        final_agg[["window_start", "avg_temperature", "avg_humidity", "avg_wind_speed", "reading_count"]].rename(
            columns={
                "window_start": "Window Start",
                "avg_temperature": "Avg Temp (°C)",
                "avg_humidity": "Avg Humidity (%)",
                "avg_wind_speed": "Avg Wind (km/h)",
                "reading_count": "Readings",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Waiting for aggregated data from ksqlDB... (updates every 5 minutes)")

# ── Pipeline Stats ──
st.header("Pipeline Stats")
col1, col2, col3 = st.columns(3)
col1.metric("Raw Readings", len(raw_list))
col2.metric("Aggregated Windows", len(agg_list))
col3.metric("Data Source", "Confluent Cloud Kafka")

st.divider()
st.caption("Live data: Lambda (1 min) -> Confluent Cloud Kafka -> ksqlDB -> Dashboard (Kafka consumer)")

# ── Auto-refresh ──
time.sleep(refresh_seconds)
st.rerun()
