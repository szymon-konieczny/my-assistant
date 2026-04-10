import sqlite3
from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_message_id TEXT NOT NULL,
    gmail_account TEXT NOT NULL,
    attachment_filename TEXT NOT NULL,
    vendor_name TEXT,
    invoice_number TEXT,
    sell_date TEXT,
    amount REAL,
    currency TEXT,
    sender_email TEXT,
    email_subject TEXT,
    email_date TEXT,
    pdf_path TEXT,
    scan_run_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(gmail_message_id, attachment_filename)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    invoices_found INTEGER DEFAULT 0,
    invoices_polish_skipped INTEGER DEFAULT 0,
    draft_created BOOLEAN DEFAULT 0,
    error_message TEXT,
    date_range_start TEXT,
    date_range_end TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.close()


def insert_invoice(
    gmail_message_id: str,
    gmail_account: str,
    attachment_filename: str,
    vendor_name: str | None,
    invoice_number: str | None,
    sell_date: str | None,
    amount: float | None,
    currency: str | None,
    sender_email: str | None,
    email_subject: str | None,
    email_date: str | None,
    pdf_path: str | None,
    scan_run_id: str | None,
) -> bool:
    """Insert an invoice record. Returns True if inserted, False if duplicate."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO invoices
            (gmail_message_id, gmail_account, attachment_filename,
             vendor_name, invoice_number, sell_date, amount, currency,
             sender_email, email_subject, email_date, pdf_path, scan_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                gmail_message_id, gmail_account, attachment_filename,
                vendor_name, invoice_number, sell_date, amount, currency,
                sender_email, email_subject, email_date, pdf_path, scan_run_id,
            ),
        )
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_invoices(month: str | None = None, page: int = 1, per_page: int = 50) -> list[dict]:
    conn = get_connection()
    offset = (page - 1) * per_page
    if month:
        rows = conn.execute(
            """SELECT * FROM invoices
            WHERE sell_date LIKE ? || '%'
            ORDER BY sell_date DESC, created_at DESC
            LIMIT ? OFFSET ?""",
            (month, per_page, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM invoices
            ORDER BY sell_date DESC, created_at DESC
            LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_totals() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT
            substr(sell_date, 1, 7) as month,
            currency,
            SUM(amount) as total,
            COUNT(*) as count
        FROM invoices
        WHERE sell_date IS NOT NULL AND amount IS NOT NULL
        GROUP BY month, currency
        ORDER BY month DESC, currency"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_grand_totals() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT
            currency,
            SUM(amount) as total,
            COUNT(*) as count
        FROM invoices
        WHERE amount IS NOT NULL
        GROUP BY currency
        ORDER BY currency"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_scan_run(run_id: str, date_range_start: str, date_range_end: str):
    conn = get_connection()
    conn.execute(
        """INSERT INTO scan_runs (id, started_at, date_range_start, date_range_end)
        VALUES (?, datetime('now'), ?, ?)""",
        (run_id, date_range_start, date_range_end),
    )
    conn.commit()
    conn.close()


def update_scan_run(run_id: str, **kwargs):
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    conn.execute(f"UPDATE scan_runs SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def get_scan_runs(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_scan_run(run_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM scan_runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_invoices_for_run(run_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM invoices WHERE scan_run_id = ? ORDER BY sell_date", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
