import logging
from datetime import datetime, timezone

from ksef2 import Client, Environment
from ksef2.domain.models.invoices import InvoicesFilter
from ksef2.domain.models.pagination import InvoiceMetadataParams

from config import settings

logger = logging.getLogger(__name__)


class KsefRateLimitError(Exception):
    """Raised when KSeF API returns 429 Too Many Requests."""
    pass


def _parse_nip(token: str) -> str:
    """Extract NIP from KSEF_TOKEN (format: ...|nip-XXXXXXXXXX|...)."""
    for part in token.split("|"):
        if part.startswith("nip-"):
            return part[4:]
    raise ValueError("Cannot parse NIP from KSEF_TOKEN. Expected format: ...|nip-XXXXXXXXXX|...")


def query_invoices(date_from: str, date_to: str) -> list[dict]:
    """Query KSeF for received invoices in the given date range.

    Args:
        date_from: YYYY-MM-DD
        date_to: YYYY-MM-DD

    Returns list of dicts with invoice fields for the frontend.
    Raises KsefRateLimitError if rate limited.
    """
    token = settings.ksef_token
    if not token:
        logger.warning("KSEF_TOKEN not configured")
        return []

    nip = _parse_nip(token)

    client = Client(environment=Environment.PRODUCTION)

    try:
        auth = client.authentication.with_token(ksef_token=token, nip=nip)

        filters = InvoicesFilter(
            role="buyer",
            date_type="issue_date",
            date_from=datetime.fromisoformat(f"{date_from}T00:00:00+00:00"),
            date_to=datetime.fromisoformat(f"{date_to}T23:59:59+00:00"),
            amount_type="brutto",
        )
        params = InvoiceMetadataParams(page_size=100, sort_order="desc")

        response = auth.invoices.query_metadata(filters=filters, params=params)
    except Exception as e:
        err = str(e)
        if "429" in err or "rate limit" in err.lower() or "Too Many Requests" in err:
            logger.warning(f"KSeF rate limited: {e}")
            raise KsefRateLimitError("KSeF rate limit exceeded. Try again in a few minutes.")
        raise

    invoices = []
    for inv in response.invoices:
        invoices.append({
            "ksef_number": inv.ksef_number,
            "invoice_number": inv.invoice_number,
            "vendor_name": inv.seller.name if inv.seller else None,
            "vendor_nip": inv.seller.nip if inv.seller else None,
            "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
            "net_amount": inv.net_amount,
            "gross_amount": inv.gross_amount,
            "vat_amount": inv.vat_amount,
            "currency": inv.currency,
            "invoice_type": inv.invoice_type,
        })

    logger.info(f"KSeF query returned {len(invoices)} invoices for {date_from} to {date_to}")
    return invoices
