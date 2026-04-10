from config import settings
from models import ExtractedInvoiceData


def is_polish_invoice(data: ExtractedInvoiceData) -> bool:
    """Check if an invoice is from a Polish vendor (for KSeF exclusion).
    Only excludes if the VENDOR is Polish, not just because the invoice
    language is Polish (e.g. Apple Ireland sends Polish-language invoices).
    """
    if data.is_polish_vendor:
        return True
    if data.vendor_country and data.vendor_country.upper() == "PL":
        return True
    return False


def is_excluded_sender(sender_email: str | None) -> bool:
    """Check if the sender should be excluded from processing."""
    if not sender_email:
        return False
    return sender_email.lower() in [s.lower() for s in settings.excluded_senders]
