from config import settings
from models import ExtractedInvoiceData


def is_polish_invoice(data: ExtractedInvoiceData) -> bool:
    """Check if an invoice is Polish based on extracted data."""
    if data.is_polish:
        return True
    if data.language and data.language.lower() in ("polish", "pl", "polski"):
        return True
    if data.currency and data.currency.upper() == "PLN":
        return True
    return False


def is_excluded_sender(sender_email: str | None) -> bool:
    """Check if the sender should be excluded from processing."""
    if not sender_email:
        return False
    return sender_email.lower() in [s.lower() for s in settings.excluded_senders]
