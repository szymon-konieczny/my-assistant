import os
import re
from config import settings


def save_invoice_pdf(
    pdf_bytes: bytes,
    sell_date: str | None,
    vendor_name: str | None,
    original_filename: str,
) -> str:
    """Save invoice PDF to the month-specific directory.
    Returns the relative path to the saved file.
    """
    if sell_date and len(sell_date) >= 7:
        month_dir = sell_date[:7]  # YYYY-MM
    else:
        month_dir = "unknown"

    dir_path = os.path.join(settings.invoice_storage_dir, month_dir)
    os.makedirs(dir_path, exist_ok=True)

    safe_vendor = _sanitize_filename(vendor_name) if vendor_name else ""
    safe_original = _sanitize_filename(os.path.splitext(original_filename)[0])

    if safe_vendor:
        filename = f"{safe_vendor}_{safe_original}.pdf"
    else:
        filename = f"{safe_original}.pdf"

    file_path = os.path.join(dir_path, filename)

    # Avoid overwriting
    counter = 1
    while os.path.exists(file_path):
        base = f"{safe_vendor}_{safe_original}" if safe_vendor else safe_original
        file_path = os.path.join(dir_path, f"{base}_{counter}.pdf")
        counter += 1

    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    return file_path


def _sanitize_filename(name: str) -> str:
    """Remove unsafe characters from a filename component."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    name = re.sub(r"\s+", "_", name)
    return name[:60]
