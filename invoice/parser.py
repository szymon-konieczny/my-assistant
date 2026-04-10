import base64
import json
import logging
import re
import time

import anthropic

from config import settings
from models import ExtractedInvoiceData

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze this invoice PDF and extract the following information.
Return ONLY a JSON object with these exact fields:

{
  "vendor_name": "The company or person who issued the invoice",
  "vendor_country": "Two-letter ISO country code of the vendor/issuer (based on their address or VAT number, e.g. PL, IE, US, DE)",
  "invoice_number": "The invoice number/ID",
  "sell_date": "The sell date (data sprzedaży) or service date in YYYY-MM-DD format. This is NOT the delivery date. If only an invoice date is present and no separate sell date, use the invoice date.",
  "amount": 1234.56,
  "currency": "Three-letter ISO currency code (e.g. EUR, USD, PLN, GBP, CZK)",
  "is_polish_vendor": false,
  "language": "detected language of the invoice"
}

Rules:
- "amount" must be a number (not a string), representing the gross/total amount (brutto)
- If multiple amounts exist, use the final total (gross/brutto)
- "is_polish_vendor" should be true ONLY if the VENDOR/ISSUER is a Polish company (registered in Poland, has a Polish NIP without country prefix or with PL prefix, address in Poland). An invoice written in Polish or using the word "faktura" from a foreign company (e.g. Apple Ireland, Google Ireland) is NOT a Polish vendor.
- "sell_date" should be the sell/service date, NOT the delivery or payment date
- If a field cannot be determined, set it to null
- Return ONLY the JSON object, no other text"""


def extract_invoice_data(pdf_bytes: bytes) -> ExtractedInvoiceData:
    """Extract structured data from an invoice PDF using Claude API."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    for attempt in range(3):
        try:
            message = client.messages.create(
                model=settings.claude_model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": EXTRACTION_PROMPT,
                            },
                        ],
                    }
                ],
            )
            response_text = message.content[0].text
            return _parse_response(response_text)

        except anthropic.RateLimitError:
            wait = 2 ** (attempt + 1)
            logger.warning(f"Rate limited, retrying in {wait}s...")
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt < 2:
                wait = 2 ** (attempt + 1)
                logger.warning(f"API error: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Failed after 3 attempts: {e}")
                raise

    raise RuntimeError("Failed to extract invoice data after retries")


def _parse_response(text: str) -> ExtractedInvoiceData:
    """Parse Claude's response into ExtractedInvoiceData."""
    try:
        data = json.loads(text)
        return ExtractedInvoiceData(**data)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return ExtractedInvoiceData(**data)
        logger.error(f"Could not parse response: {text[:200]}")
        return ExtractedInvoiceData()
