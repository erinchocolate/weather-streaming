# Real-Time Weather Stream Processing Pipeline

We have 12 chickens and want to understand how weather affects their egg production. This project is the first step: building a real-time pipeline to collect and store weather data for our location so we can later correlate it with egg-laying patterns.

It ingests weather data from the Open-Meteo API for Palmerston North using AWS Lambda, streams it through Confluent Cloud Kafka with ksqlDB stream processing, and stores results in an S3 data lake queryable via Athena. All AWS infrastructure is provisioned with Terraform.

## Architecture

```
EventBridge (every 1 min)
        |
  AWS Lambda (Producer)
        |
        v
Confluent Cloud Kafka [weather-raw]
        |
        ├── ksqlDB (5-min Tumbling Window) ──> [weather-aggregated]
        |                                            |
        ├── S3 Sink Connector ──> S3 ──> Athena      |
        |                         (raw data)         |
        |                                            |
        └── S3 Sink Connector ──────────> S3 ──> Athena
                                          (aggregated data)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Serverless Compute | AWS Lambda + EventBridge | Scheduled data ingestion |
| Message Broker | Confluent Cloud (Apache Kafka) | Event streaming |
| Stream Processing | ksqlDB (Confluent Cloud) | Real-time windowed aggregation |
| Data Lake Storage | Amazon S3 | Raw + aggregated data store |
| Data Catalog | AWS Glue | Schema metadata for Athena |
| Query Engine | Amazon Athena | Serverless SQL on S3 data |
| Data Connectors | Confluent S3 Sink Connectors | Kafka to S3 integration |
| Infrastructure as Code | Terraform | AWS resource provisioning |
| Language | Python 3.12 | Producer logic |
| Local Dev | Docker Compose | Local Kafka + PostgreSQL |

## Cloud Deployment

### Prerequisites

- AWS CLI configured (`aws configure`)
- Confluent Cloud account with a Kafka cluster
- Terraform installed

### 1. Provision AWS infrastructure with Terraform

```bash
cd terraform
# Create terraform.tfvars with your Confluent Cloud credentials (see variables.tf for required values)

terraform init
terraform plan
terraform apply
```

This creates: Lambda function, EventBridge schedule, S3 buckets, Glue catalog (database + tables), Athena workgroup, and IAM roles.

### 2. Set up ksqlDB on Confluent Cloud

In the Confluent Cloud console, create a ksqlDB application and run the statements from `ksqldb/statements.sql`:

```sql
-- Create source stream
CREATE STREAM weather_raw_stream (
    city        VARCHAR KEY,
    latitude    DOUBLE,
    longitude   DOUBLE,
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

-- Create 5-minute tumbling window aggregation
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
```

### 3. Set up S3 Sink Connectors on Confluent Cloud

Create two S3 Sink Connectors in Confluent Cloud:

| Connector | Topic | S3 Destination |
|-----------|-------|----------------|
| S3 Sink 0 | `weather-raw` | `s3://<bucket>/topics/weather-raw/` |
| S3 Sink 1 | `weather-aggregated` | `s3://<bucket>/topics/weather-aggregated/` |

### 4. Query with Athena

Once data lands in S3, load partitions and query:

```sql
MSCK REPAIR TABLE weather_raw;
MSCK REPAIR TABLE weather_aggregated;

-- Latest weather readings
SELECT city, temperature_c, humidity_pct, wind_speed_kmh, observed_at
FROM weather_raw
ORDER BY observed_at DESC
LIMIT 10;

-- 5-minute aggregated averages
SELECT
    from_unixtime(window_start / 1000) AS window_start,
    from_unixtime(window_end / 1000) AS window_end,
    avg_temperature,
    avg_humidity,
    avg_wind_speed,
    reading_count
FROM weather_aggregated
ORDER BY window_start DESC;
```

### 5. Test Lambda manually

```bash
aws lambda invoke --function-name weather-producer --region ap-southeast-2 /tmp/output.json && cat /tmp/output.json
```

## Local Development

For local development and testing, a Docker Compose setup is included:

```bash
# Start local Kafka, ksqlDB, PostgreSQL, Kafdrop
docker compose up -d

# Install Python dependencies
pip install -r requirements.txt

# Run producer locally
python producer/weather_producer.py

# Run consumer locally (writes to local PostgreSQL)
python consumer/weather_consumer.py
```

Access local services:
- **Kafdrop** (Kafka topic browser): http://localhost:9000
- **ksqlDB**: http://localhost:8088
- **PostgreSQL**: `localhost:5433`

## Project Structure

```
streaming/
├── docker-compose.yml              # Local dev infrastructure (6 services)
├── requirements.txt                # Python dependencies
├── producer/
│   └── weather_producer.py         # Open-Meteo API -> Kafka (local)
├── consumer/
│   └── weather_consumer.py         # Kafka -> PostgreSQL (local)
├── dashboard/
│   └── app.py                      # Weather data dashboard
├── lambda/
│   ├── weather_producer_lambda.py  # Lambda version of producer
│   └── deploy.sh                   # Lambda deployment script
├── terraform/
│   ├── main.tf                     # AWS resources (Lambda, S3, Glue, Athena)
│   ├── variables.tf                # Input variables
│   └── outputs.tf                  # Output values
├── ksqldb/
│   └── statements.sql              # ksqlDB stream + aggregation
├── db/
│   └── init.sql                    # PostgreSQL schema (local dev)
├── analytics/
│   └── queries.sql                 # Example analytical queries
├── aws/                            # AWS CLI bundle (gitignored dist/)
```

## Next Steps

- Track daily egg counts per chicken and store alongside weather data
- Analyse correlations between weather variables (temperature, humidity, pressure) and egg production
- Build a simple dashboard to visualise trends over time

## What This Demonstrates

- **Serverless compute**: AWS Lambda triggered by EventBridge for scheduled data ingestion
- **Event-driven architecture**: Confluent Cloud Kafka as the central message broker
- **Stream processing**: ksqlDB tumbling window aggregation computing 5-minute averages in real time
- **Data lake**: S3 + Glue + Athena for serverless analytics on streaming data
- **Kafka Connect**: Managed S3 Sink Connectors for code-free data movement
- **Infrastructure as Code**: Terraform provisioning all AWS resources
- **Python data processing**: Producer/consumer pattern with the official Confluent Kafka client
- **SQL**: Athena queries on S3 data lake, ksqlDB stream processing, PostgreSQL analytical queries

## Teardown

```bash
# AWS resources
cd terraform && terraform destroy

# Local Docker
docker compose down
```
