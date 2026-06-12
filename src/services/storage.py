import aioboto3
import boto3
from tenacity import retry, stop_after_attempt, wait_exponential
from ..core.config import settings, BUCKETS
from ..core.logging import logger

session = aioboto3.Session()


def _client_kwargs():
    return dict(
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        region_name="us-east-1",
    )


def ensure_buckets():
    try:
        client = boto3.client("s3", **_client_kwargs())
        for name in BUCKETS.values():
            try:
                client.head_bucket(Bucket=name)
            except Exception:
                client.create_bucket(Bucket=name)
                logger.info("bucket_created", bucket=name)
            # Make bucket publicly readable
            client.put_bucket_policy(
                Bucket=name,
                Policy=(
                    '{"Version":"2012-10-17","Statement":['
                    '{"Effect":"Allow","Principal":"*","Action":"s3:GetObject",'
                    f'"Resource":"arn:aws:s3:::{name}/*"'
                    "}]}"
                ),
            )
    except Exception as e:
        logger.warning(
            "minio_not_available",
            error=str(e),
            hint="Start MinIO before uploading files",
        )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
async def upload_file(bucket: str, key: str, data: bytes, content_type: str, metadata: dict = {}):
    async with session.client("s3", **_client_kwargs()) as s3:
        await s3.put_object(
            Bucket=bucket, Key=key, Body=data,
            ContentType=content_type,
            Metadata={k: str(v) for k, v in metadata.items()},
        )
    logger.info("file_uploaded", bucket=bucket, key=key, size=len(data))


async def delete_file(bucket: str, key: str):
    async with session.client("s3", **_client_kwargs()) as s3:
        await s3.delete_object(Bucket=bucket, Key=key)
    logger.info("file_deleted", bucket=bucket, key=key)

async def get_signed_url(bucket: str, key: str, expires: int = 3600) -> str:
    async with session.client("s3", **_client_kwargs()) as s3:
        return await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
