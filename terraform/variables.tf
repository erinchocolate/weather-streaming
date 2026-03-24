variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

variable "kafka_bootstrap_servers" {
  description = "Confluent Cloud Kafka bootstrap servers"
  type        = string
  sensitive   = true
}

variable "kafka_api_key" {
  description = "Confluent Cloud API key"
  type        = string
  sensitive   = true
}

variable "kafka_api_secret" {
  description = "Confluent Cloud API secret"
  type        = string
  sensitive   = true
}
