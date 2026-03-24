output "s3_data_lake_bucket" {
  value = aws_s3_bucket.data_lake.bucket
}

output "lambda_function_name" {
  value = aws_lambda_function.weather_producer.function_name
}

output "glue_database" {
  value = aws_glue_catalog_database.weather.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.weather.name
}
