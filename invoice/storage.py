import logging
import re

import boto3
from botocore.config import Config as BotoConfig

from config import settings

logger = logging.getLogger(__name__)

_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3_client


def save_invoice_pdf(
    pdf_bytes: bytes,
    sell_date: str | None,
    vendor_name: str | None,
    original_filename: str,
) -> str:
    """Upload invoice PDF to R2 bucket.
    Returns the R2 object key.
    """
    if sell_date and len(sell_date) >= 7:
        year = sell_date[:4]
        month = sell_date[5:7]
        month_dir = f"{year}/{month}"  # YYYY/MM
    else:
        month_dir = "unknown"

    safe_vendor = _sanitize_filename(vendor_name) if vendor_name else ""
    safe_original = _sanitize_filename(re.sub(r"\.pdf$", "", original_filename, flags=re.IGNORECASE))

    if safe_vendor:
        filename = f"{safe_vendor}_{safe_original}.pdf"
    else:
        filename = f"{safe_original}.pdf"

    key = f"{month_dir}/{filename}"

    client = _get_s3_client()

    # Check if key exists, append counter if so
    counter = 1
    original_key = key
    while True:
        try:
            client.head_object(Bucket=settings.r2_bucket, Key=key)
            # Exists — try next name
            base = original_key.rsplit(".pdf", 1)[0]
            key = f"{base}_{counter}.pdf"
            counter += 1
        except client.exceptions.ClientError:
            break

    client.put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    logger.info(f"  Uploaded to R2: {key}")
    return key


def get_invoice_pdf(key: str) -> bytes:
    """Download an invoice PDF from R2."""
    client = _get_s3_client()
    response = client.get_object(Bucket=settings.r2_bucket, Key=key)
    return response["Body"].read()


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from a filename component."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    name = re.sub(r"\s+", "_", name)
    return name[:60]
