"""SQLite persists articles between runs; a URL is unique within a topic."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def connect(path):
    db = sqlite3.connect(str(path), timeout=20)
    db.row_factory = sqlite3.Row
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS articles (
            topic TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL,
            text TEXT NOT NULL, source TEXT NOT NULL, published_at TEXT,
            date_precision TEXT NOT NULL, collected_at TEXT NOT NULL,
            UNIQUE(topic, url))""")


def save_articles(path, topic, articles):
    inserted = 0
    with connect(path) as db:
        for article in articles:
            cursor = db.execute("""INSERT OR IGNORE INTO articles
                (topic,url,title,text,source,published_at,date_precision,collected_at)
                VALUES (?,?,?,?,?,?,?,?)""", (
                topic.casefold(), article["url"], article["title"], article["text"],
                article["source"], article.get("published_at"),
                article.get("date_precision", "unknown"),
                datetime.now(timezone.utc).isoformat()))
            inserted += cursor.rowcount
    return inserted


def read_articles(path, topic):
    with connect(path) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM articles WHERE topic=? ORDER BY published_at DESC",
            (topic.casefold(),))]


def topics(path):
    with connect(path) as db:
        return [r[0] for r in db.execute("SELECT DISTINCT topic FROM articles ORDER BY topic")]
