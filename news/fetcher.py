import html
import logging
import re
from datetime import datetime, timezone
from time import mktime

import feedparser

import db

logger = logging.getLogger(__name__)


def _clean_html(text: str | None) -> str | None:
    """Strip HTML tags and decode entities from RSS summary."""
    if not text:
        return None
    clean = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(clean).strip()
    # Truncate long summaries
    if len(clean) > 500:
        clean = clean[:497] + "..."
    return clean


def _parse_date(entry) -> str | None:
    """Extract published date from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            dt = datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    return None


def fetch_feed(feed_url: str, feed_name: str, category_id: int) -> int:
    """Fetch and store articles from a single RSS feed. Returns count of new articles."""
    try:
        parsed = feedparser.parse(feed_url)
    except Exception as e:
        logger.error(f"Failed to parse feed {feed_url}: {e}")
        return 0

    new_count = 0
    for entry in parsed.entries[:20]:  # Limit per feed
        title = entry.get("title")
        if not title:
            continue

        link = entry.get("link")
        summary = _clean_html(entry.get("summary") or entry.get("description"))
        published = _parse_date(entry)

        inserted = db.insert_news_article(
            category_id=category_id,
            title=title,
            summary=summary,
            source_url=link,
            source_name=feed_name,
            published_at=published,
        )
        if inserted:
            new_count += 1

    return new_count


def fetch_all_feeds() -> int:
    """Fetch articles from all configured feeds. Returns total new articles."""
    feeds = db.get_news_feeds()
    total = 0
    for feed in feeds:
        count = fetch_feed(feed["feed_url"], feed["name"], feed["category_id"])
        if count:
            logger.info(f"  {feed['name']}: {count} new articles")
        total += count
    logger.info(f"News fetch complete: {total} new articles")
    return total
