terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

# ──────────────────────────────────────────────
# S3 Bucket (Data Lake)
# ──────────────────────────────────────────────

resource "aws_s3_bucket" "data_lake" {
  bucket = "weather-streaming-data-${data.aws_caller_identity.current.account_id}"
}

# ──────────────────────────────────────────────
# Glue Catalog (for Athena)
# ──────────────────────────────────────────────

resource "aws_glue_catalog_database" "weather" {
  name = "weather"
}

resource "aws_glue_catalog_table" "weather_raw" {
  name          = "weather_raw"
  database_name = aws_glue_catalog_database.weather.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "json"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.bucket}/topics/weather-raw/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "city"
      type = "string"
    }
    columns {
      name = "latitude"
      type = "double"
    }
    columns {
      name = "longitude"
      type = "double"
    }
    columns {
      name = "temperature_c"
      type = "double"
    }
    columns {
      name = "humidity_pct"
      type = "double"
    }
    columns {
      name = "wind_speed_kmh"
      type = "double"
    }
    columns {
      name = "precipitation_mm"
      type = "double"
    }
    columns {
      name = "pressure_hpa"
      type = "double"
    }
    columns {
      name = "cloud_cover_pct"
      type = "double"
    }
    columns {
      name = "observed_at"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "weather_aggregated" {
  name          = "weather_aggregated"
  database_name = aws_glue_catalog_database.weather.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "json"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.bucket}/topics/weather-aggregated/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "window_start"
      type = "bigint"
    }
    columns {
      name = "window_end"
      type = "bigint"
    }
    columns {
      name = "avg_temperature"
      type = "double"
    }
    columns {
      name = "avg_humidity"
      type = "double"
    }
    columns {
      name = "avg_wind_speed"
      type = "double"
    }
    columns {
      name = "reading_count"
      type = "bigint"
    }
  }
}

# ──────────────────────────────────────────────
# IAM Role for Lambda
# ──────────────────────────────────────────────

resource "aws_iam_role" "lambda_role" {
  name = "weather-producer-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ──────────────────────────────────────────────
# Lambda Function (Weather Producer)
# ──────────────────────────────────────────────

resource "aws_lambda_function" "weather_producer" {
  function_name = "weather-producer"
  role          = aws_iam_role.lambda_role.arn
  handler       = "weather_producer_lambda.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 128

  filename         = "${path.module}/lambda-package.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda-package.zip")

  environment {
    variables = {
      KAFKA_BOOTSTRAP_SERVERS = var.kafka_bootstrap_servers
      KAFKA_API_KEY           = var.kafka_api_key
      KAFKA_API_SECRET        = var.kafka_api_secret
    }
  }
}

# ──────────────────────────────────────────────
# EventBridge Schedule (triggers Lambda every 15 min)
# ──────────────────────────────────────────────

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "weather-producer-schedule"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.weather_producer.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.weather_producer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# ──────────────────────────────────────────────
# Athena Workgroup + Results Bucket
# ──────────────────────────────────────────────

resource "aws_s3_bucket" "athena_results" {
  bucket = "weather-athena-results-${data.aws_caller_identity.current.account_id}"
}

resource "aws_athena_workgroup" "weather" {
  name = "weather-pipeline"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"
    }
  }
}
