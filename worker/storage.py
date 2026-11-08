"""Read/write text objects either in S3-compatible object storage (s3://bucket/key)
or on the local file system (any other path). boto3 is only imported for s3:// URIs.

S3 settings come from the environment: S3_ENDPOINT, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY (the keys are injected from a Kubernetes Secret).
"""
import os
from pathlib import Path


def is_s3(uri):
    return str(uri).startswith("s3://")


def split_s3(uri):
    rest = str(uri)[len("s3://"):]
    bucket, _, key = rest.partition("/")
    return bucket, key


_client = None


def s3_client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}),
        )
    return _client


def read_text(uri):
    if is_s3(uri):
        bucket, key = split_s3(uri)
        return s3_client().get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    return Path(uri).read_text(encoding="utf-8")


def exists(uri):
    if is_s3(uri):
        bucket, key = split_s3(uri)
        try:
            s3_client().head_object(Bucket=bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - any error means "not readable"
            return False
    return Path(uri).exists()


def write_text(uri, text):
    data = text.encode("utf-8")
    if is_s3(uri):
        bucket, key = split_s3(uri)
        s3_client().put_object(Bucket=bucket, Key=key, Body=data)
    else:
        p = Path(uri)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def list_uris(prefix_uri):
    """All object URIs (or files) directly under a prefix / directory, sorted."""
    if is_s3(prefix_uri):
        bucket, prefix = split_s3(prefix_uri)
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        out = []
        for page in s3_client().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            out += [f"s3://{bucket}/{o['Key']}" for o in page.get("Contents", [])]
        return sorted(out)
    return sorted(str(p) for p in Path(prefix_uri).iterdir() if p.is_file())


def join(prefix_uri, name):
    return str(prefix_uri).rstrip("/") + "/" + name
