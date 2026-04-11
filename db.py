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

CREATE TABLE IF NOT EXISTS email_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmail_account TEXT NOT NULL,
    digest_date TEXT NOT NULL,
    content TEXT NOT NULL,
    email_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(gmail_account, digest_date)
);

CREATE TABLE IF NOT EXISTS news_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES news_categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER,
    title TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    source_name TEXT,
    published_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    UNIQUE(source_url)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


DEFAULT_NEWS_FEEDS = {
    "AI": [
        ("Anthropic News", "https://www.anthropic.com/rss.xml"),
        ("OpenAI Blog", "https://openai.com/blog/rss.xml"),
        ("Google AI Blog", "https://blog.google/technology/ai/rss/"),
        ("MIT Tech Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ],
    "Technology": [
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("Hacker News", "https://hnrss.org/frontpage"),
    ],
}


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    # Migrate: add is_ksef column if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()]
    if "is_ksef" not in cols:
        conn.execute("ALTER TABLE invoices ADD COLUMN is_ksef BOOLEAN DEFAULT 0")
        conn.commit()
    # Seed default news categories and feeds
    existing = conn.execute("SELECT COUNT(*) FROM news_categories").fetchone()[0]
    if existing == 0:
        for cat_name, feeds in DEFAULT_NEWS_FEEDS.items():
            conn.execute("INSERT INTO news_categories (name) VALUES (?)", (cat_name,))
            cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for feed_name, feed_url in feeds:
                conn.execute(
                    "INSERT INTO news_feeds (category_id, name, feed_url) VALUES (?, ?, ?)",
                    (cat_id, feed_name, feed_url),
                )
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


# --- News ---

def get_news_categories() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM news_categories ORDER BY name").fetchall()
    categories = []
    for r in rows:
        cat = dict(r)
        feeds = conn.execute(
            "SELECT * FROM news_feeds WHERE category_id = ?", (r["id"],)
        ).fetchall()
        cat["feeds"] = [dict(f) for f in feeds]
        categories.append(cat)
    conn.close()
    return categories


def get_news_feeds() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT nf.*, nc.name as category_name
        FROM news_feeds nf JOIN news_categories nc ON nf.category_id = nc.id"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_news_category(name: str, feeds: list[dict]) -> int:
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("INSERT INTO news_categories (name) VALUES (?)", (name,))
    cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for f in feeds:
        conn.execute(
            "INSERT INTO news_feeds (category_id, name, feed_url) VALUES (?, ?, ?)",
            (cat_id, f["name"], f["feed_url"]),
        )
    conn.commit()
    conn.close()
    return cat_id


def delete_news_category(category_id: int):
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM news_articles WHERE category_id = ?", (category_id,))
    conn.execute("DELETE FROM news_feeds WHERE category_id = ?", (category_id,))
    conn.execute("DELETE FROM news_categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()


def insert_news_article(
    category_id: int,
    title: str,
    summary: str | None,
    source_url: str | None,
    source_name: str | None,
    published_at: str | None,
) -> bool:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO news_articles
            (category_id, title, summary, source_url, source_name, published_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (category_id, title, summary, source_url, source_name, published_at),
        )
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_news_articles(category_id: int | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    if category_id:
        rows = conn.execute(
            """SELECT * FROM news_articles WHERE category_id = ?
            ORDER BY published_at DESC LIMIT ?""",
            (category_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM news_articles ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Email Digests ---

def save_digest(gmail_account: str, digest_date: str, content: str, email_count: int) -> bool:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO email_digests
            (gmail_account, digest_date, content, email_count)
            VALUES (?, ?, ?, ?)""",
            (gmail_account, digest_date, content, email_count),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_digest(digest_date: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM email_digests WHERE digest_date = ? ORDER BY created_at DESC LIMIT 1",
        (digest_date,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_digest_dates(limit: int = 30) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT digest_date FROM email_digests ORDER BY digest_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [r["digest_date"] for r in rows]
