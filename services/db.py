import boto3 # type: ignore
from .config import AWS_ENDPOINT_URL, AWS_REGION

def get_dynamodb_resource():
    return boto3.resource(
        "dynamodb",
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION
    )
