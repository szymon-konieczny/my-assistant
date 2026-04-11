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
    is_ksef BOOLEAN DEFAULT 0,
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
    # Migrate: add is_ksef column if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()]
    if "is_ksef" not in cols:
        conn.execute("ALTER TABLE invoices ADD COLUMN is_ksef BOOLEAN DEFAULT 0")
        conn.commit()
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
    is_ksef: bool = False,
) -> bool:
    """Insert an invoice record. Returns True if inserted, False if duplicate."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO invoices
            (gmail_message_id, gmail_account, attachment_filename,
             vendor_name, invoice_number, sell_date, amount, currency,
             sender_email, email_subject, email_date, pdf_path, scan_run_id,
             is_ksef)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                gmail_message_id, gmail_account, attachment_filename,
                vendor_name, invoice_number, sell_date, amount, currency,
                sender_email, email_subject, email_date, pdf_path, scan_run_id,
                is_ksef,
            ),
        )
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def invoice_number_exists(invoice_number: str) -> bool:
    """Check if an invoice with this number already exists."""
    if not invoice_number:
        return False
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM invoices WHERE invoice_number = ? LIMIT 1",
        (invoice_number,),
    ).fetchone()
    conn.close()
    return row is not None


def get_invoices(month: str | None = None, is_ksef: bool | None = None, page: int = 1, per_page: int = 50) -> list[dict]:
    conn = get_connection()
    offset = (page - 1) * per_page
    where = []
    params: list = []
    if month:
        where.append("sell_date LIKE ? || '%'")
        params.append(month)
    if is_ksef is not None:
        where.append("is_ksef = ?")
        params.append(is_ksef)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"""SELECT * FROM invoices {clause}
        ORDER BY sell_date DESC, created_at DESC
        LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_totals(is_ksef: bool | None = None) -> list[dict]:
    conn = get_connection()
    where = "WHERE sell_date IS NOT NULL AND amount IS NOT NULL"
    params: list = []
    if is_ksef is not None:
        where += " AND is_ksef = ?"
        params.append(is_ksef)
    rows = conn.execute(
        f"""SELECT
            substr(sell_date, 1, 7) as month,
            currency,
            SUM(amount) as total,
            COUNT(*) as count
        FROM invoices
        {where}
        GROUP BY month, currency
        ORDER BY month DESC, currency""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_grand_totals(is_ksef: bool | None = None) -> list[dict]:
    conn = get_connection()
    where = "WHERE amount IS NOT NULL"
    params: list = []
    if is_ksef is not None:
        where += " AND is_ksef = ?"
        params.append(is_ksef)
    rows = conn.execute(
        f"""SELECT
            currency,
            SUM(amount) as total,
            COUNT(*) as count
        FROM invoices
        {where}
        GROUP BY currency
        ORDER BY currency""",
        params,
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


def get_invoices_by_date_range(after_date: str, before_date: str) -> list[dict]:
    """Get all invoices with sell_date in the given range (inclusive)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM invoices
        WHERE sell_date >= ? AND sell_date <= ?
        ORDER BY sell_date""",
        (after_date, before_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_invoices_for_run(run_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM invoices WHERE scan_run_id = ? ORDER BY sell_date", (run_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
