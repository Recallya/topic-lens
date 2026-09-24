"""Pure calculations: publication dates, word frequencies, and time buckets."""
import calendar
import random
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

WIB = timezone(timedelta(hours=7))
STOPWORDS = set("""yang dan di ke dari ini itu untuk dengan pada adalah dalam akan
tidak juga sebagai oleh atau para bisa sudah saat menjadi ada lebih telah karena
kata mengatakan tersebut namun hingga serta antara kepada tentang sebuah tahun
hari bulan jakarta indonesia the a an and of to in is are was were for on with
as by at from this that it its be has have had not but or after before into over
their they said says will can new news com www http https html read more juga
kami kita dia mereka saya anda nya sebuah secara kini masih sangat melalui
berita mengungkapkan menurut dilakukan all how why what who when than been
would could should you your our we us them he she his her some many much""".split())


def parse_date(value):
    """Unzoned timestamps are WIB; date-only values retain day precision."""
    if not value:
        return None, "unknown"
    value = str(value).strip()
    precision = "day" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else "time"
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None, "unknown"
    if date.tzinfo is None:
        date = date.replace(tzinfo=WIB)
    return date.astimezone(timezone.utc).isoformat(), precision


def five_years_ago(now):
    year = now.year - 5
    return now.replace(year=year, day=min(now.day, calendar.monthrange(year, now.month)[1]))


def matches_topic(topic, text):
    words = re.findall(r"\w+", topic.casefold())
    return bool(words) and all(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text.casefold()) for word in words)


def floor_bucket(date, granularity):
    date = date.astimezone(WIB)
    if granularity == "yearly":
        return date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == "monthly":
        return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == "daily":
        return date.replace(hour=0, minute=0, second=0, microsecond=0)
    return date.replace(minute=(date.minute // 10) * 10, second=0, microsecond=0)


def next_bucket(date, granularity):
    if granularity == "yearly":
        return date.replace(year=date.year + 1)
    if granularity == "monthly":
        return date.replace(year=date.year + (date.month == 12), month=date.month % 12 + 1)
    return date + (timedelta(days=1) if granularity == "daily" else timedelta(minutes=10))


def analyze(articles, granularity, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(WIB)
    start = now - timedelta(hours=5) if granularity == "hours" else five_years_ago(now)
    counts, selected = Counter(), []
    unknown = 0
    for article in articles:
        raw = article.get("published_at")
        if not raw:
            unknown += 1
            continue
        date = datetime.fromisoformat(raw).astimezone(WIB)
        if granularity == "hours" and article.get("date_precision") != "time":
            continue
        if start <= date <= now:
            selected.append(article)
            counts[floor_bucket(date, granularity).isoformat()] += 1
    buckets = []
    cursor = floor_bucket(start, granularity)
    while cursor <= now:
        key = cursor.isoformat()
        buckets.append({"date": key, "count": counts.get(key)})
        cursor = next_bucket(cursor, granularity)
    tokens = Counter()
    for article in selected:
        tokens.update(w for w in re.findall(r"[^\W\d_]+", (article["title"] + " " + article["text"]).casefold())
                      if len(w) > 2 and w not in STOPWORDS)
    peak = max((b for b in buckets if b["count"]), key=lambda b: b["count"], default=None)
    return {"series": buckets, "words": [{"word": w, "count": n} for w, n in tokens.most_common(55)],
            "total": len(selected), "stored": len(articles), "sources": len({a["source"] for a in selected}),
            "unknown_dates": unknown, "peak": peak, "start": start.isoformat(), "end": now.isoformat(),
            "observed_buckets": len(counts), "total_buckets": len(buckets),
            "articles": sorted(selected, key=lambda a: a["published_at"], reverse=True)[:80]}


def demo_articles(topic, now=None):
    """Synthetic fixtures for the UI; never written to the database."""
    now = now or datetime.now(timezone.utc)
    rng = random.Random(topic.casefold())
    vocabulary = ["inovasi", "teknologi", "riset", "digital", "investasi", "industri", "ekonomi",
                  "masyarakat", "pengembangan", "pendidikan", "kebijakan", "peluang", "kolaborasi"]
    result = []
    for index in range(470):
        days = rng.randrange(0, 1824) if index > 39 else 0
        date = now - timedelta(days=days, minutes=rng.randrange(1, 299))
        words = rng.choices(vocabulary, weights=[12, 10, 8, 7, 5, 5, 4, 3, 3, 2, 2, 1, 1], k=35)
        result.append({"title": f"[DEMO] {topic}: {words[0]} dan {words[1]}",
                       "text": " ".join(words), "url": "", "source": "Sumber demo " + str(index % 4 + 1),
                       "published_at": date.isoformat(), "date_precision": "time"})
    return result
