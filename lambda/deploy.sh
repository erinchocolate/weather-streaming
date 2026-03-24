#!/bin/bash
set -e

FUNCTION_NAME="weather-producer"
REGION="ap-southeast-2"
SCHEDULE_RATE="rate(1 minute)"
ROLE_NAME="weather-producer-lambda-role"

echo "=== Building Lambda package ==="
rm -rf /tmp/lambda-build /tmp/lambda-package.zip
mkdir -p /tmp/lambda-build

pip install confluent-kafka requests -t /tmp/lambda-build --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 --no-deps
# requests dependencies
pip install charset-normalizer idna urllib3 certifi -t /tmp/lambda-build --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

cp weather_producer_lambda.py /tmp/lambda-build/

cd /tmp/lambda-build
zip -r /tmp/lambda-package.zip .
echo "Package size: $(du -h /tmp/lambda-package.zip | cut -f1)"

echo "=== Creating IAM role ==="
TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

ROLE_ARN=$(aws iam create-role \
  --role-name $ROLE_NAME \
  --assume-role-policy-document "$TRUST_POLICY" \
  --query 'Role.Arn' --output text 2>/dev/null || \
  aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)

aws iam attach-role-policy --role-name $ROLE_NAME \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true

echo "Role ARN: $ROLE_ARN"
echo "Waiting for role to propagate..."
sleep 10

echo "=== Creating/Updating Lambda function ==="
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION 2>/dev/null; then
  aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb:///tmp/lambda-package.zip \
    --region $REGION
else
  aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.12 \
    --handler weather_producer_lambda.handler \
    --role $ROLE_ARN \
    --zip-file fileb:///tmp/lambda-package.zip \
    --timeout 30 \
    --memory-size 128 \
    --region $REGION \
    --environment "Variables={KAFKA_BOOTSTRAP_SERVERS=$KAFKA_BOOTSTRAP_SERVERS,KAFKA_API_KEY=$KAFKA_API_KEY,KAFKA_API_SECRET=$KAFKA_API_SECRET}"
fi

echo "=== Setting up EventBridge schedule ==="
RULE_ARN=$(aws events put-rule \
  --name weather-producer-schedule \
  --schedule-expression "$SCHEDULE_RATE" \
  --region $REGION \
  --query 'RuleArn' --output text)

FUNCTION_ARN=$(aws lambda get-function \
  --function-name $FUNCTION_NAME \
  --region $REGION \
  --query 'Configuration.FunctionArn' --output text)

aws lambda add-permission \
  --function-name $FUNCTION_NAME \
  --statement-id weather-schedule-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn $RULE_ARN \
  --region $REGION 2>/dev/null || true

aws events put-targets \
  --rule weather-producer-schedule \
  --targets "Id=weather-producer,Arn=$FUNCTION_ARN" \
  --region $REGION

echo ""
echo "=== Done ==="
echo "Lambda function: $FUNCTION_NAME"
echo "Schedule: $SCHEDULE_RATE"
echo "Region: $REGION"
echo ""
echo "Test manually with:"
echo "  aws lambda invoke --function-name $FUNCTION_NAME --region $REGION /tmp/lambda-output.json && cat /tmp/lambda-output.json"
