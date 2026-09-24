"""Regression tests for date accuracy, deduplication, parsing, and API behavior."""
import io
import re
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from analytics import analyze, five_years_ago, matches_topic, parse_date
from app import create_app
from crawler import Crawler, parse_feed, parse_html, validate_url
from storage import initialize, read_articles, save_articles


def article(date, precision="time", url="https://example.com/a"):
    return {"title": "Teknologi energi", "text": "Energi dan inovasi energi", "source": "example.com",
            "published_at": date, "date_precision": precision, "url": url}


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 24, 13, 30, tzinfo=timezone.utc)

    def test_missing_intervals_are_not_zero_and_words_follow_period(self):
        result = analyze([article("2026-09-24T12:00:00+00:00"), article("2010-01-01T00:00:00+00:00")], "monthly", self.now)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["series"][-1]["count"], 1)
        self.assertIsNone(result["series"][0]["count"])
        self.assertEqual(result["words"][0], {"word": "energi", "count": 3})

    def test_five_hours_excludes_old_future_unknown_and_date_only(self):
        values = [article((self.now - timedelta(hours=h)).isoformat()) for h in (0, 4, 5, 6, -1)]
        values += [article(None), article(self.now.isoformat(), "day")]
        result = analyze(values, "hours", self.now)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["unknown_dates"], 1)

    def test_wib_midnight_and_all_granularities(self):
        values = [article("2026-09-23T18:00:00+00:00")]
        result = analyze(values, "daily", self.now)
        self.assertTrue(result["peak"]["date"].startswith("2026-09-24"))
        for granularity in ("yearly", "monthly", "daily"):
            self.assertEqual(sum(p["count"] or 0 for p in analyze(values, granularity, self.now)["series"]), 1)

    def test_leap_day_and_exact_rolling_window(self):
        date = datetime(2024, 2, 29, tzinfo=timezone.utc)
        self.assertEqual(five_years_ago(date).day, 28)
        cutoff = five_years_ago(self.now)
        values = [article(cutoff.isoformat()), article((cutoff - timedelta(seconds=1)).isoformat())]
        self.assertEqual(analyze(values, "yearly", self.now)["total"], 1)

    def test_dates_do_not_invent_publication_time(self):
        self.assertEqual(parse_date("garbage"), (None, "unknown"))
        self.assertEqual(parse_date("2025-01-01")[1], "day")
        self.assertEqual(parse_date("2025-01-01T07:00:00")[0], "2025-01-01T00:00:00+00:00")
        self.assertEqual(parse_date("Thu, 24 Sep 2026 10:00:00 GMT")[1], "time")

    def test_topic_matching_word_boundaries(self):
        self.assertTrue(matches_topic("energi bersih", "Bersih dengan ENERGI baru"))
        self.assertFalse(matches_topic("AI", "lain ramai baik"))


class CrawlerTests(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = b'<rss><channel><item><title>Teknologi</title><link>https://example.com/a</link><description>Energi baru</description><pubDate>Thu, 24 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(parse_feed(rss, "https://example.com/rss")[0]["published_at"], "2026-09-24T10:00:00+00:00")
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Energi</title><link href="/a"/><published>2026-09-24T10:00:00Z</published><summary>Teknologi</summary></entry></feed>'
        self.assertEqual(parse_feed(atom, "https://example.com/rss")[0]["url"], "https://example.com/a")

    def test_html_dates_and_boilerplate(self):
        html = '<html><h1>Teknologi</h1><nav><p>Menu</p></nav><script type="application/ld+json">{"@graph":[{"datePublished":"2025-01-01"}]}</script><article><p>Inovasi energi.</p></article></html>'
        result = parse_html(html, "https://example.com/a")
        self.assertEqual(result["text"], "Inovasi energi.")
        self.assertEqual(result["date_precision"], "day")
        self.assertIsNone(parse_html("<h1>Unknown</h1>", "https://example.com")["published_at"])

    def test_private_urls_rejected(self):
        for url in ("file:///etc/passwd", "http://user:password@example.com", "https://example.com:8000"):
            with self.assertRaises(ValueError):
                validate_url(url)
        with patch("crawler.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with self.assertRaises(ValueError):
                validate_url("http://example.com")

    def test_crawl_filters_deduplicates_and_limits(self):
        feed = b'<rss><channel><item><title>Energi teknologi</title><link>https://example.com/a</link></item><item><title>Energi</title><link>https://example.com/a</link></item><item><title>Olahraga</title><link>https://example.com/b</link></item></channel></rss>'
        with patch.object(Crawler, "fetch", return_value=(feed, "https://example.com/rss", "application/xml")):
            results, warnings, checked = Crawler().crawl(["https://example.com/rss"], "Energi", 20, lambda value: None)
        self.assertEqual(len(results), 1)
        self.assertEqual(checked, 2)
        self.assertEqual(warnings, [])

    def test_robots_disallow(self):
        crawler = Crawler()
        with patch.object(crawler, "fetch", return_value=(b"User-agent: *\nDisallow: /private", "", "text/plain")):
            self.assertFalse(crawler.allowed("https://example.com/private/a"))
            self.assertTrue(crawler.allowed("https://example.com/news"))
        crawler.session.close()


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.app = create_app(self.path)
        self.app.testing = True
        self.client = self.app.test_client()
        page = self.client.get("/").get_data(as_text=True)
        self.token = re.search(r'name="topiclens-token" content="([^"]+)"', page).group(1)
        self.headers = {"X-TopicLens-Token": self.token}

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_demo_and_assets(self):
        self.assertEqual(self.client.get("/api/analysis?topic=Energi").json["total"], 0)
        for period in ("yearly", "monthly", "daily", "hours"):
            result = self.client.get(f"/api/analysis?topic=Energi&demo=1&granularity={period}").json
            self.assertTrue(result["demo"])
            self.assertGreater(result["total"], 0)
        self.assertEqual(read_articles(self.path, "Energi"), [])
        for asset in ("style.css", "app.js"):
            with self.client.get("/static/" + asset) as response:
                self.assertEqual(response.status_code, 200)

    def test_import_dedup_and_validation(self):
        csv = "title,text,url,published_at\nEnergi,inovasi,https://example.com/a,2026-09-01\nOlahraga,bola,https://example.com/b,2026-09-01\nEnergi,riset,https://example.com/c,bad\n"
        def upload():
            return self.client.post("/api/import", headers=self.headers, data={"topic": "Energi", "file": (io.BytesIO(csv.encode()), "archive.csv")})
        result = upload()
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.json["added"], result.json["skipped"], result.json["invalid"]), (1, 1, 1))
        self.assertEqual(upload().json["duplicates"], 1)
        self.assertEqual(read_articles(self.path, "energi")[0]["date_precision"], "day")

    def test_api_errors_and_write_token(self):
        self.assertEqual(self.client.post("/api/crawl", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/crawl", headers=self.headers, json={"topic": "Energi", "sources": []}).status_code, 400)
        self.assertEqual(self.client.get("/api/analysis?granularity=invalid").status_code, 400)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)

    def test_sqlite_persists_and_topic_is_case_insensitive(self):
        initialize(self.path)
        row = article("2026-09-24T12:00:00+00:00")
        self.assertEqual(save_articles(self.path, "Energi", [row, row]), 1)
        self.assertEqual(len(read_articles(self.path, "ENERGI")), 1)

    def test_background_job_saves_articles_and_reports_completion(self):
        row = article("2026-09-24T12:00:00+00:00")
        with patch("app.Crawler.crawl", return_value=([row], [], 1)):
            result = self.client.post("/api/crawl", headers=self.headers,
                                      json={"topic": "Energi", "sources": ["antara"], "limit": 20})
            self.assertEqual(result.status_code, 202)
            for _ in range(100):
                job = self.client.get("/api/jobs/" + result.json["id"]).json
                if job["state"] != "running":
                    break
                time.sleep(0.01)
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["added"], 1)
        self.assertEqual(len(read_articles(self.path, "Energi")), 1)


if __name__ == "__main__":
    unittest.main()
